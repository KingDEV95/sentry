from __future__ import annotations

import enum
import errno
import hashlib
import logging
import os
import os.path
import re
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Container, Iterable, Mapping
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone
from symbolic.debuginfo import Archive, BcSymbolMap, Object, UuidMapping, normalize_debug_id
from symbolic.exceptions import ObjectErrorUnsupportedObject, SymbolicError

from sentry import options
from sentry.backup.scopes import RelocationScope
from sentry.constants import KNOWN_DIF_FORMATS
from sentry.db.models import (
    BoundedBigIntegerField,
    FlexibleForeignKey,
    JSONField,
    Model,
    region_silo_model,
    sane_repr,
)
from sentry.db.models.manager.base import BaseManager
from sentry.models.files.file import File
from sentry.models.files.utils import clear_cached_files
from sentry.utils import json, metrics
from sentry.utils.zip import safe_extract_zip

if TYPE_CHECKING:
    from sentry.models.project import Project

logger = logging.getLogger(__name__)

DIF_MIMETYPES = {v: k for k, v in KNOWN_DIF_FORMATS.items()}

_proguard_file_re = re.compile(r"/proguard/(?:mapping-)?(.*?)\.txt$")


class BadDif(Exception):
    pass


class ProjectDebugFileManager(BaseManager["ProjectDebugFile"]):
    def find_missing(self, checksums: Iterable[str], project: Project) -> list[str]:
        if not checksums:
            return []

        checksums = [x.lower() for x in checksums]
        missing = set(checksums)

        found = ProjectDebugFile.objects.filter(
            checksum__in=checksums, project_id=project.id
        ).values_list("checksum", flat=True)

        missing.difference_update(checksum for checksum in found if checksum is not None)

        return sorted(missing)

    def find_by_debug_ids(
        self, project: Project, debug_ids: Container[str], features: Iterable[str] | None = None
    ) -> dict[str, ProjectDebugFile]:
        """Finds debug information files matching the given debug identifiers.

        If a set of features is specified, only files that satisfy all features
        will be returned. This does not apply to legacy debug files that were
        not tagged with features.

        Returns a dict of debug files keyed by their debug identifier.
        """
        features = frozenset(features) if features is not None else frozenset()

        query = Q(project_id=project.id, debug_id__in=debug_ids)
        difs = list(ProjectDebugFile.objects.filter(query).select_related("file").order_by("-id"))

        # because otherwise this would be a circular import:
        from sentry.debug_files.debug_files import maybe_renew_debug_files

        maybe_renew_debug_files(difs)

        difs_by_id: dict[str, list[ProjectDebugFile]] = {}
        for dif in difs:
            difs_by_id.setdefault(dif.debug_id, []).append(dif)

        rv = {}
        for debug_id, group in difs_by_id.items():
            with_features = [dif for dif in group if "features" in (dif.data or ())]

            # In case we've never computed features for any of these files, we
            # just take the first one and assume that it matches.
            if not with_features:
                rv[debug_id] = group[0]
                continue

            # There's at least one file with computed features. Older files are
            # considered redundant and will be deleted. We search for the first
            # file matching the given feature set. This might not resolve if no
            # DIF matches the given feature set.
            for dif in with_features:
                if dif.features >= features:
                    rv[debug_id] = dif
                    break

        return rv


@region_silo_model
class ProjectDebugFile(Model):
    __relocation_scope__ = RelocationScope.Excluded

    file = FlexibleForeignKey("sentry.File")
    checksum = models.CharField(max_length=40, null=True, db_index=True)
    object_name = models.TextField()
    cpu_name = models.CharField(max_length=40)
    project_id = BoundedBigIntegerField(null=True, db_index=True)
    debug_id = models.CharField(max_length=64, db_column="uuid")
    code_id = models.CharField(max_length=64, null=True)
    data: models.Field[dict[str, Any] | None, dict[str, Any] | None] = JSONField(null=True)
    date_accessed = models.DateTimeField(default=timezone.now, db_default=Now())

    objects: ClassVar[ProjectDebugFileManager] = ProjectDebugFileManager()

    difcache: ClassVar[DIFCache]

    class Meta:
        indexes = (
            models.Index(fields=("project_id", "debug_id")),
            models.Index(fields=("project_id", "code_id")),
        )
        db_table = "sentry_projectdsymfile"
        app_label = "sentry"

    __repr__ = sane_repr("object_name", "cpu_name", "debug_id")

    @property
    def file_format(self) -> str:
        ct = self.file.headers.get("Content-Type", "unknown").lower()
        return KNOWN_DIF_FORMATS.get(ct, "unknown")

    @property
    def file_type(self) -> str | None:
        if self.data:
            val: Any | None = self.data.get("type")
            if isinstance(val, str) or val is None:
                return val
            else:
                logger.error("Incorrect type stored for file_type: %r", val)
                return None
        else:
            return None

    @property
    def file_extension(self) -> str:
        if self.file_format == "breakpad":
            return ".sym"
        if self.file_format == "macho":
            return "" if self.file_type == "exe" else ".dSYM"
        if self.file_format == "proguard":
            return ".txt"
        if self.file_format == "elf":
            return "" if self.file_type == "exe" else ".debug"
        if self.file_format == "pe":
            return ".exe" if self.file_type == "exe" else ".dll"
        if self.file_format == "pdb" or self.file_format == "portablepdb":
            return ".pdb"
        if self.file_format == "sourcebundle":
            return ".src.zip"
        if self.file_format == "wasm":
            return ".wasm"
        if self.file_format == "bcsymbolmap":
            return ".bcsymbolmap"
        if self.file_format == "uuidmap":
            return ".plist"
        if self.file_format == "il2cpp":
            return ".json"

        return ""

    @property
    def features(self) -> frozenset[str]:
        return frozenset((self.data or {}).get("features", []))

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        ret = super().delete(*args, **kwargs)
        self.file.delete()
        return ret


def clean_redundant_difs(project: Project, debug_id: str) -> None:
    """Deletes redundant debug files from the database and file storage. A debug
    file is considered redundant if there is a newer file with the same debug
    identifier and the same or a superset of its features.
    """
    difs = (
        ProjectDebugFile.objects.filter(project_id=project.id, debug_id=debug_id)
        .select_related("file")
        .order_by("-id")
    )

    all_features: set[str] = set()
    bcsymbolmap_seen = False
    uuidmap_seen = False
    il2cpp_seen = False
    for i, dif in enumerate(difs):
        mime_type = dif.file.headers.get("Content-Type")
        if mime_type == DIF_MIMETYPES["bcsymbolmap"]:
            if not bcsymbolmap_seen:
                bcsymbolmap_seen = True
            else:
                dif.delete()
        elif mime_type == DIF_MIMETYPES["uuidmap"]:
            if not uuidmap_seen:
                uuidmap_seen = True
            else:
                dif.delete()
        elif mime_type == DIF_MIMETYPES["il2cpp"]:
            if not il2cpp_seen:
                il2cpp_seen = True
            else:
                dif.delete()
        else:
            # We always keep the latest file. If it has no features, likely the
            # previous files did not have features either and will be removed, or we
            # keep both. Subsequent uploads will remove this file later.
            if i > 0 and dif.features <= all_features:
                dif.delete()
            else:
                all_features.update(dif.features)


def create_dif_from_id(
    project: Project,
    meta: DifMeta,
    fileobj: BinaryIO | None = None,
    file: File | None = None,
) -> tuple[ProjectDebugFile, bool]:
    """Creates the :class:`ProjectDebugFile` entry for the provided DIF.

    This creates the :class:`ProjectDebugFile` entry for the DIF provided in `meta` (a
    :class:`DifMeta` object).  If the correct entry already exists this simply returns the
    existing entry.

    It intentionally does not validate the file, only will ensure a :class:`File` entry
    exists and set its `ContentType` according to the provided :class:DifMeta`.

    Returns a tuple of `(dif, created)` where `dif` is the `ProjectDebugFile` instance and
    `created` is a bool.
    """
    if meta.file_format == "proguard":
        object_name = "proguard-mapping"
    elif meta.file_format in (
        "macho",
        "elf",
        "pdb",
        "pe",
        "portablepdb",
        "wasm",
        "sourcebundle",
        "bcsymbolmap",
        "uuidmap",
        "il2cpp",
    ):
        object_name = meta.name
    elif meta.file_format == "breakpad":
        object_name = meta.name[:-4] if meta.name.endswith(".sym") else meta.name
    else:
        raise TypeError(f"unknown dif type {meta.file_format!r}")

    if file is not None:
        checksum = file.checksum
    elif fileobj is not None:
        h = hashlib.sha1()
        while True:
            chunk = fileobj.read(16384)
            if not chunk:
                break
            h.update(chunk)
        checksum = h.hexdigest()
        fileobj.seek(0, 0)
    else:
        raise RuntimeError("missing file object")

    dif = (
        ProjectDebugFile.objects.select_related("file")
        .filter(
            project_id=project.id, debug_id=meta.debug_id, checksum=checksum, data__isnull=False
        )
        .order_by("-id")
        .first()
    )

    if dif is not None:
        return dif, False

    if file is None:
        file = File.objects.create(
            name=meta.debug_id,
            type="project.dif",
            headers={"Content-Type": DIF_MIMETYPES[meta.file_format]},
        )
        file.putfile(fileobj)
    else:
        file.type = "project.dif"
        file.headers["Content-Type"] = DIF_MIMETYPES[meta.file_format]
        file.save()

    metrics.distribution(
        "storage.put.size",
        file.size,
        tags={"usecase": "debug-files", "compression": "none"},
        unit="byte",
    )

    dif = ProjectDebugFile.objects.create(
        file=file,
        checksum=file.checksum,
        debug_id=meta.debug_id,
        code_id=meta.code_id,
        cpu_name=meta.arch,
        object_name=object_name,
        project_id=project.id,
        data=meta.data,
    )

    # The DIF we've just created might actually be removed here again. But since
    # this can happen at any time in near or distant future, we don't care and
    # assume a successful upload. The DIF will be reported to the uploader and
    # reprocessing can start.
    clean_redundant_difs(project, meta.debug_id)

    return dif, True


def _analyze_progard_filename(filename: str | None) -> str | None:
    if filename is None:
        return None

    match = _proguard_file_re.search(filename)
    if match is None:
        return None

    ident = match.group(1)

    try:
        return str(uuid.UUID(ident))
    except Exception:
        return None


@region_silo_model
class ProguardArtifactRelease(Model):
    __relocation_scope__ = RelocationScope.Excluded

    organization_id = BoundedBigIntegerField()
    project_id = BoundedBigIntegerField()
    release_name = models.CharField(max_length=250)
    proguard_uuid = models.UUIDField(db_index=True)
    project_debug_file = FlexibleForeignKey("sentry.ProjectDebugFile")
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_proguardartifactrelease"

        unique_together = (("project_id", "release_name", "proguard_uuid"),)


class DifMeta:
    def __init__(
        self,
        file_format: str,
        arch: str,
        debug_id: str,
        path: str,
        code_id: str | None = None,
        name: str | None = None,
        data: Any | None = None,
    ):
        self.file_format = file_format
        self.arch = arch
        self.debug_id = debug_id  # TODO(flub): should this use normalize_debug_id()?
        self.code_id = code_id
        self.path = path
        self.data = data

        if name is not None:
            self.name = os.path.basename(name)
        elif path is not None:
            self.name = os.path.basename(path)

    @classmethod
    def from_object(
        cls,
        obj: Object,
        path: str,
        name: str | None = None,
        debug_id: str | None = None,
    ) -> DifMeta:
        if debug_id is not None:
            try:
                debug_id = normalize_debug_id(debug_id)
            except SymbolicError:
                debug_id = None

        # Only allow overrides in the debug_id's age if the rest of the debug id
        # matches with what we determine from the object file. We generally
        # trust the server more than the client.
        obj_id = obj.debug_id
        if obj_id and debug_id and obj_id[:36] == debug_id[:36]:
            obj_id = debug_id

        return cls(
            file_format=obj.file_format,
            arch=obj.arch,
            debug_id=obj_id,
            code_id=obj.code_id,
            path=path,
            # TODO: Extract the object name from the object
            name=name,
            data={"type": obj.kind, "features": list(obj.features)},
        )

    @property
    def basename(self) -> str:
        return os.path.basename(self.path)


class DifKind(enum.Enum):
    """The different kind of DIF files we can handle."""

    Object = enum.auto()
    BcSymbolMap = enum.auto()
    UuidMap = enum.auto()
    Il2Cpp = enum.auto()
    # TODO(flub): should we include proguard?  The tradeoff is that we'd be matching the
    # regex of it twice.  That cost is probably not too great to worry about.


def determine_dif_kind(path: str) -> DifKind:
    """Returns the :class:`DifKind` detected at `path`."""
    # TODO(flub): Using just the filename might be sufficient.  But the cost of opening a
    # file that we'll open and parse right away anyway is rather minimal, though it would
    # save a syscall.
    with open(path, "rb") as fp:
        data = fp.read(11)
        if data.startswith(b"BCSymbolMap"):
            return DifKind.BcSymbolMap
        elif data.startswith(b"<?xml"):
            return DifKind.UuidMap
        elif data.startswith(b"{"):  # lol
            return DifKind.Il2Cpp
        else:
            return DifKind.Object


def detect_dif_from_path(
    path: str,
    name: str | None = None,
    debug_id: str | None = None,
    accept_unknown: bool = False,
) -> list[DifMeta]:
    """Detects which kind of Debug Information File (DIF) the file at `path` is.

    :param accept_unknown: If this is ``False`` an exception will be logged with the error
       when a file which is not a known DIF is found.  This is useful for when ingesting ZIP
       files directly from Apple App Store Connect which you know will also contain files
       which are not DIFs.

    :returns: an array since an Archive can contain more than one Object.

    :raises BadDif: If the file is not a valid DIF.
    """
    # Proguard files have a path or a name like (proguard/UUID.txt) or
    # (proguard/mapping-UUID.txt).
    proguard_id = _analyze_progard_filename(path) or _analyze_progard_filename(name)
    if proguard_id is not None:
        data = {"features": ["mapping"]}
        return [
            DifMeta(
                file_format="proguard",
                arch="any",
                debug_id=proguard_id,
                code_id=None,
                path=path,
                name=name,
                data=data,
            )
        ]

    dif_kind = determine_dif_kind(path)
    if dif_kind == DifKind.BcSymbolMap:
        if debug_id is None:
            # In theory we could also parse debug_id from the filename here.  However we
            # would need to validate that it is a valid debug_id ourselves as symbolic does
            # not expose this yet.
            raise BadDif("Missing debug_id for BCSymbolMap")
        try:
            BcSymbolMap.open(path)
        except SymbolicError as e:
            logger.debug("File failed to load as BCSymbolmap: %s", path)
            raise BadDif("Invalid BCSymbolMap: %s" % e)
        else:
            logger.debug("File loaded as BCSymbolMap: %s", path)
            return [
                DifMeta(
                    file_format="bcsymbolmap", arch="any", debug_id=debug_id, name=name, path=path
                )
            ]
    elif dif_kind == DifKind.UuidMap:
        if debug_id is None:
            # Assume the basename is the debug_id, if it wasn't symbolic will fail.  This is
            # required for when we get called for files extracted from a zipfile.
            basename = os.path.basename(path)
            try:
                debug_id = normalize_debug_id(os.path.splitext(basename)[0])
            except SymbolicError as e:
                logger.debug("Filename does not look like a debug ID: %s", path)
                raise BadDif("Invalid UuidMap: %s" % e)
        try:
            UuidMapping.from_plist(debug_id, path)
        except SymbolicError as e:
            logger.debug("File failed to load as UUIDMap: %s", path)
            raise BadDif("Invalid UuidMap: %s" % e)
        else:
            logger.debug("File loaded as UUIDMap: %s", path)
            return [
                DifMeta(file_format="uuidmap", arch="any", debug_id=debug_id, name=name, path=path)
            ]
    elif dif_kind == DifKind.Il2Cpp:
        if debug_id is None:
            raise BadDif("Missing debug_id for il2cpp")
        try:
            with open(path, "rb") as fp:
                json.load(fp)
        except json.JSONDecodeError as e:
            logger.debug("File failed to load as il2cpp: %s", path)
            raise BadDif("Invalid il2cpp: %s" % e)
        else:
            logger.debug("File loaded as il2cpp: %s", path)
            return [
                DifMeta(file_format="il2cpp", arch="any", debug_id=debug_id, name=name, path=path)
            ]
    else:
        # native debug information files (MachO, ELF or Breakpad)
        try:
            archive = Archive.open(path)
        except ObjectErrorUnsupportedObject as e:
            raise BadDif("Unsupported debug information file: %s" % e)
        except SymbolicError as e:
            if accept_unknown:
                level = logging.DEBUG
            else:
                level = logging.WARNING
            logger.log(level, "dsymfile.bad-fat-object", exc_info=True)
            raise BadDif("Invalid debug information file: %s" % e)
        else:
            objs = []
            for obj in archive.iter_objects():
                objs.append(DifMeta.from_object(obj, path, name=name, debug_id=debug_id))
            logger.debug("File is Archive with %s objects: %s", len(objs), path)
            return objs


def create_debug_file_from_dif(
    to_create: Iterable[DifMeta], project: Project
) -> list[ProjectDebugFile]:
    """Create a ProjectDebugFile from a dif (Debug Information File) and
    return an array of created objects.
    """
    rv = []
    for meta in to_create:
        with open(meta.path, "rb") as f:
            dif, created = create_dif_from_id(project, meta, fileobj=f)
            if created:
                rv.append(dif)
    return rv


def create_files_from_dif_zip(
    fileobj: BinaryIO | zipfile.ZipFile, project: Project, accept_unknown: bool = False
) -> list[ProjectDebugFile]:
    """Creates all missing debug files from the given zip file.  This
    returns a list of all files created.
    """
    from sentry.lang.native.sources import record_last_upload

    scratchpad = tempfile.mkdtemp()
    try:
        safe_extract_zip(fileobj, scratchpad)
        to_create: list[DifMeta] = []

        for dirpath, dirnames, filenames in os.walk(scratchpad):
            for fn in filenames:
                fn = os.path.join(dirpath, fn)
                try:
                    difs = detect_dif_from_path(fn, accept_unknown=accept_unknown)
                except BadDif:
                    difs = []
                to_create = to_create + difs

        rv = create_debug_file_from_dif(to_create, project)

        record_last_upload(project)

        return rv
    finally:
        shutil.rmtree(scratchpad)


class DIFCache:
    @property
    def cache_path(self) -> str:
        return options.get("dsym.cache-path")

    def get_project_path(self, project: Project) -> str:
        return os.path.join(self.cache_path, str(project.id))

    def fetch_difs(
        self, project: Project, debug_ids: Iterable[str], features: Iterable[str] | None = None
    ) -> Mapping[str, str]:
        """Given some ids returns an id to path mapping for where the
        debug symbol files are on the FS.
        """
        debug_ids = [str(debug_id).lower() for debug_id in debug_ids]
        difs = ProjectDebugFile.objects.find_by_debug_ids(project, debug_ids, features)

        rv = {}
        for debug_id, dif in difs.items():
            dif_path = os.path.join(self.get_project_path(project), debug_id)
            try:
                os.stat(dif_path)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
                dif.file.save_to(dif_path)
            rv[debug_id] = dif_path

        return rv

    def clear_old_entries(self) -> None:
        clear_cached_files(self.cache_path)


ProjectDebugFile.difcache = DIFCache()
