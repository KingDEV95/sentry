from sentry.grouping.strategies.base import ReturnedVariants


def remove_non_stacktrace_variants(variants: ReturnedVariants) -> ReturnedVariants:
    """This is a utility function that when given multiple variants will
    mark all variants as non contributing that do not contain any stacktraces
    if any of the other variants contain a stacktrace that contributes.
    """
    if len(variants) <= 1:
        return variants
    any_stacktrace_contributes = False
    non_contributing_components = []
    stacktrace_variants = set()

    # If at least one variant has a contributing stacktrace, we want to mark all variants without a
    # stacktrace as non-contributing.
    for variant_name, component in variants.items():
        stacktrace_iter = component.iter_subcomponents(
            id="stacktrace", recursive=True, only_contributing=True
        )
        if next(stacktrace_iter, None) is not None:
            any_stacktrace_contributes = True
            stacktrace_variants.add(variant_name)
        else:
            non_contributing_components.append(component)

    if any_stacktrace_contributes:
        if len(stacktrace_variants) == 1:
            hint_suffix = "the %s variant does" % next(iter(stacktrace_variants))
        else:
            # this branch is basically dead because we only have two
            # variants right now, but this is so this does not break in
            # the future.
            hint_suffix = "others do"
        for component in non_contributing_components:
            component.update(
                contributes=False,
                hint="ignored because this variant does not have a contributing "
                "stacktrace, but %s" % hint_suffix,
            )

    return variants


def has_url_origin(path: str, files_count_as_urls: bool) -> bool:
    # URLs can be generated such that they are:
    #   blob:http://example.com/7f7aaadf-a006-4217-9ed5-5fbf8585c6c0
    # https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL
    if not path:
        return False
    if path.startswith(("http:", "https:", "applewebdata:", "blob:")):
        return True
    if path.startswith("file:"):
        return files_count_as_urls
    return False
