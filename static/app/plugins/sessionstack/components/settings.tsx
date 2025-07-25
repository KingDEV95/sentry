import isEqual from 'lodash/isEqual';

import {Alert} from 'sentry/components/core/alert';
import {Button} from 'sentry/components/core/button';
import Form from 'sentry/components/deprecatedforms/form';
import FormState from 'sentry/components/forms/state';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {t} from 'sentry/locale';
import DefaultSettings from 'sentry/plugins/components/settings';

type Props = DefaultSettings['props'];

type State = DefaultSettings['state'] & {
  // NB: "On-premises" here refers to on-premises SessionStack, not Sentry.
  // That said, we only support connecting to an on-premises SessionStack from
  // a self-hosted Sentry: https://docs.sessionstack.com/docs/sentry.

  showOnPremisesConfiguration?: boolean;
};

class Settings extends DefaultSettings<Props, State> {
  REQUIRED_FIELDS = ['account_email', 'api_token', 'website_id'];
  ON_PREMISES_FIELDS = ['api_url', 'player_url'];

  renderFields(fields: State['fieldList']) {
    return fields?.map(f =>
      this.renderField({
        config: f,
        formData: this.state.formData,
        formErrors: this.state.errors,
        onChange: this.changeField.bind(this, f.name),
      })
    );
  }

  filterFields(fields: State['fieldList'], fieldNames: string[]) {
    return fields?.filter(field => fieldNames.includes(field.name)) ?? [];
  }

  toggleOnPremisesConfiguration = () => {
    this.setState({
      showOnPremisesConfiguration: !this.state.showOnPremisesConfiguration,
    });
  };

  render() {
    if (this.state.state === FormState.LOADING) {
      return <LoadingIndicator />;
    }

    if (this.state.state === FormState.ERROR && !this.state.fieldList) {
      return (
        <Alert.Container>
          <Alert type="error" showIcon={false}>
            An unknown error occurred. Need help with this?{' '}
            <a href="https://sentry.io/support/">Contact support</a>
          </Alert>
        </Alert.Container>
      );
    }

    const isSaving = this.state.state === FormState.SAVING;
    const hasChanges = !isEqual(this.state.initialData, this.state.formData);

    const requiredFields = this.filterFields(this.state.fieldList, this.REQUIRED_FIELDS);
    const onPremisesFields = this.filterFields(
      this.state.fieldList,
      this.ON_PREMISES_FIELDS
    );

    return (
      <Form onSubmit={this.onSubmit} submitDisabled={isSaving || !hasChanges}>
        {this.state.errors.__all__ && (
          <Alert type="error" showIcon={false}>
            <ul>
              <li>{this.state.errors.__all__}</li>
            </ul>
          </Alert>
        )}
        {this.renderFields(requiredFields)}
        {onPremisesFields.length > 0 ? (
          <div className="control-group">
            <Button type="button" onClick={this.toggleOnPremisesConfiguration}>
              {t('Configure on-premises')}
            </Button>
          </div>
        ) : null}
        {this.state.showOnPremisesConfiguration
          ? this.renderFields(onPremisesFields)
          : null}
      </Form>
    );
  }
}

export default Settings;
