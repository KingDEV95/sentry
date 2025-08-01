import type {ReactElement} from 'react';
import {Fragment} from 'react';
import {NavLink as RouterNavLink} from 'react-router-dom';
import styled from '@emotion/styled';
import type {LocationDescriptor} from 'history';

import {Badge} from 'sentry/components/core/badge';
import {FeatureBadge} from 'sentry/components/core/badge/featureBadge';
import {Tooltip} from 'sentry/components/core/tooltip';
import HookOrDefault from 'sentry/components/hookOrDefault';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import {locationDescriptorToTo} from 'sentry/utils/reactRouter6Compat/location';
import {isChonkTheme} from 'sentry/utils/theme/withChonk';

type Props = {
  label: React.ReactNode;
  to: LocationDescriptor;
  badge?: string | number | null | ReactElement;
  id?: string;
  index?: boolean;
  onClick?: (e: React.MouseEvent) => void;
};

const LabelHook = HookOrDefault({
  hookName: 'sidebar:item-label',
  defaultComponent: ({children}) => <Fragment>{children}</Fragment>,
});

function SettingsNavItemDeprecated({badge, label, index, id, to, ...props}: Props) {
  let renderedBadge: React.ReactNode;

  if (badge === 'new') {
    renderedBadge = <FeatureBadge type="new" />;
  } else if (badge === 'beta') {
    renderedBadge = <FeatureBadge type="beta" />;
  } else if (badge === 'alpha') {
    renderedBadge = <FeatureBadge type="alpha" />;
  } else if (badge === 'warning') {
    renderedBadge = (
      <Tooltip title={t('This setting needs review')} position="right">
        <StyledBadge type="warning">{badge}</StyledBadge>
      </Tooltip>
    );
  } else if (typeof badge === 'string' || typeof badge === 'number') {
    renderedBadge = <StyledBadge type="default">{badge}</StyledBadge>;
  } else {
    renderedBadge = badge;
  }

  return (
    <StyledNavItem end={index} to={locationDescriptorToTo(to)} {...props}>
      <LabelHook id={id}>{label}</LabelHook>
      {badge ? renderedBadge : null}
    </StyledNavItem>
  );
}

const StyledNavItem = styled(RouterNavLink)`
  display: flex;
  gap: ${space(0.75)};
  align-items: center;
  color: ${p => p.theme.subText};
  font-size: 14px;
  line-height: 30px;
  position: relative;

  &.active {
    color: ${p =>
      isChonkTheme(p.theme) ? p.theme.tokens.content.accent : p.theme.textColor};

    &:before {
      background: ${p =>
        isChonkTheme(p.theme) ? p.theme.tokens.graphics.accent : p.theme.active};
    }
  }

  &:hover,
  &:focus,
  &:active {
    color: ${p => p.theme.textColor};
    outline: none;
  }

  &:focus-visible {
    outline: none;
    background: ${p => p.theme.backgroundSecondary};
    padding-left: 15px;
    margin-left: -15px;
    border-radius: 3px;

    &:before {
      left: -15px;
    }
  }

  &:before {
    position: absolute;
    content: '';
    display: block;
    top: 4px;
    left: -30px;
    height: 20px;
    width: 4px;
    background: transparent;
    border-radius: 0 2px 2px 0;
  }
`;

const StyledBadge = styled(Badge)`
  font-weight: ${p => p.theme.fontWeight.normal};
  height: auto;
  line-height: 1;
  font-size: ${p => p.theme.fontSize.xs};
  padding: 3px ${space(0.75)};
  vertical-align: middle;
`;

export default SettingsNavItemDeprecated;
