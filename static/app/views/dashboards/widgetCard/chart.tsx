import type React from 'react';
import {Component} from 'react';
import type {Theme} from '@emotion/react';
import {withTheme} from '@emotion/react';
import styled from '@emotion/styled';
import type {LegendComponentOption} from 'echarts';
import type {Location} from 'history';
import isEqual from 'lodash/isEqual';
import omit from 'lodash/omit';

import {AreaChart} from 'sentry/components/charts/areaChart';
import {BarChart} from 'sentry/components/charts/barChart';
import ChartZoom from 'sentry/components/charts/chartZoom';
import {getFormatter} from 'sentry/components/charts/components/tooltip';
import ErrorPanel from 'sentry/components/charts/errorPanel';
import {LineChart} from 'sentry/components/charts/lineChart';
import ReleaseSeries from 'sentry/components/charts/releaseSeries';
import SimpleTableChart from 'sentry/components/charts/simpleTableChart';
import TransitionChart from 'sentry/components/charts/transitionChart';
import TransparentLoadingMask from 'sentry/components/charts/transparentLoadingMask';
import {getSeriesSelection, isChartHovered} from 'sentry/components/charts/utils';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import type {PlaceholderProps} from 'sentry/components/placeholder';
import Placeholder from 'sentry/components/placeholder';
import {IconWarning} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {PageFilters} from 'sentry/types/core';
import type {
  EChartDataZoomHandler,
  EChartEventHandler,
  ReactEchartsRef,
} from 'sentry/types/echarts';
import type {Confidence, Organization} from 'sentry/types/organization';
import {defined} from 'sentry/utils';
import {
  axisLabelFormatter,
  axisLabelFormatterUsingAggregateOutputType,
  getDurationUnit,
  tooltipFormatter,
} from 'sentry/utils/discover/charts';
import type {EventsMetaType, MetaType} from 'sentry/utils/discover/eventView';
import {type RenderFunctionBaggage} from 'sentry/utils/discover/fieldRenderers';
import type {AggregationOutputType, DataUnit, Sort} from 'sentry/utils/discover/fields';
import {
  aggregateOutputType,
  getAggregateArg,
  getEquation,
  getMeasurementSlug,
  isAggregateField,
  isEquation,
  maybeEquationAlias,
  stripDerivedMetricsPrefix,
  stripEquationPrefix,
} from 'sentry/utils/discover/fields';
import getDynamicText from 'sentry/utils/getDynamicText';
import {decodeSorts} from 'sentry/utils/queryString';
import {getDatasetConfig} from 'sentry/views/dashboards/datasetConfig/base';
import type {Widget} from 'sentry/views/dashboards/types';
import {DisplayType, WidgetType} from 'sentry/views/dashboards/types';
import {eventViewFromWidget} from 'sentry/views/dashboards/utils';
import {getBucketSize} from 'sentry/views/dashboards/utils/getBucketSize';
import WidgetLegendNameEncoderDecoder from 'sentry/views/dashboards/widgetLegendNameEncoderDecoder';
import type WidgetLegendSelectionState from 'sentry/views/dashboards/widgetLegendSelectionState';
import {BigNumberWidgetVisualization} from 'sentry/views/dashboards/widgets/bigNumberWidget/bigNumberWidgetVisualization';
import type {TabularColumn} from 'sentry/views/dashboards/widgets/common/types';
import {TableWidgetVisualization} from 'sentry/views/dashboards/widgets/tableWidget/tableWidgetVisualization';
import {
  convertTableDataToTabularData,
  decodeColumnAliases,
} from 'sentry/views/dashboards/widgets/tableWidget/utils';
import {decodeColumnOrder} from 'sentry/views/discover/utils';
import {ConfidenceFooter} from 'sentry/views/explore/spans/charts/confidenceFooter';

import type {GenericWidgetQueriesChildrenProps} from './genericWidgetQueries';

const OTHER = 'Other';
const PERCENTAGE_DECIMAL_POINTS = 3;

type TableResultProps = Pick<
  GenericWidgetQueriesChildrenProps,
  'errorMessage' | 'loading' | 'tableResults'
>;

type WidgetCardChartProps = Pick<
  GenericWidgetQueriesChildrenProps,
  'timeseriesResults' | 'tableResults' | 'errorMessage' | 'loading'
> & {
  location: Location;
  organization: Organization;
  selection: PageFilters;
  theme: Theme;
  widget: Widget;
  widgetLegendState: WidgetLegendSelectionState;
  chartGroup?: string;
  confidence?: Confidence;
  disableZoom?: boolean;
  expandNumbers?: boolean;
  isMobile?: boolean;
  isSampled?: boolean | null;
  legendOptions?: LegendComponentOption;
  minTableColumnWidth?: number;
  noPadding?: boolean;
  onLegendSelectChanged?: EChartEventHandler<{
    name: string;
    selected: Record<string, boolean>;
    type: 'legendselectchanged';
  }>;
  onWidgetTableResizeColumn?: (columns: TabularColumn[]) => void;
  onWidgetTableSort?: (sort: Sort) => void;
  onZoom?: EChartDataZoomHandler;
  sampleCount?: number;
  shouldResize?: boolean;
  showConfidenceWarning?: boolean;
  showLoadingText?: boolean;
  timeseriesResultsTypes?: Record<string, AggregationOutputType>;
  windowWidth?: number;
};

class WidgetCardChart extends Component<WidgetCardChartProps> {
  shouldComponentUpdate(nextProps: WidgetCardChartProps): boolean {
    if (
      this.props.widget.displayType === DisplayType.BIG_NUMBER &&
      nextProps.widget.displayType === DisplayType.BIG_NUMBER &&
      (this.props.windowWidth !== nextProps.windowWidth ||
        !isEqual(this.props.widget?.layout, nextProps.widget?.layout))
    ) {
      return true;
    }

    // Widget title changes should not update the WidgetCardChart component tree
    const currentProps = {
      ...omit(this.props, ['windowWidth']),
      widget: {
        ...this.props.widget,
        title: '',
      },
    };

    nextProps = {
      ...omit(nextProps, ['windowWidth']),
      widget: {
        ...nextProps.widget,
        title: '',
      },
    };

    return !isEqual(currentProps, nextProps);
  }

  tableResultComponent({loading, tableResults}: TableResultProps): React.ReactNode {
    const {
      widget,
      selection,
      minTableColumnWidth,
      location,
      organization,
      theme,
      onWidgetTableSort,
      onWidgetTableResizeColumn,
    } = this.props;
    if (loading || !tableResults?.[0]) {
      // Align height to other charts.
      return <LoadingPlaceholder />;
    }

    const datasetConfig = getDatasetConfig(widget.widgetType);

    const getCustomFieldRenderer = (
      field: string,
      meta: MetaType,
      org?: Organization
    ) => {
      return datasetConfig.getCustomFieldRenderer?.(field, meta, widget, org) || null;
    };

    return tableResults.map((result, i) => {
      const fields = widget.queries[i]?.fields?.map(stripDerivedMetricsPrefix) ?? [];
      const fieldAliases = widget.queries[i]?.fieldAliases ?? [];
      const fieldHeaderMap = datasetConfig.getFieldHeaderMap?.() ?? {};
      const eventView = eventViewFromWidget(widget.title, widget.queries[0]!, selection);
      const columns = decodeColumnOrder(
        fields.map(field => ({
          field,
        })),
        tableResults[i]?.meta
      ).map((column, index) => ({
        key: column.key,
        width: widget.tableWidths?.[index] ?? minTableColumnWidth ?? column.width,
        type: column.type === 'never' ? null : column.type,
        sortable:
          widget.widgetType === WidgetType.RELEASE ? isAggregateField(column.key) : true,
      }));
      const aliases = decodeColumnAliases(columns, fieldAliases, fieldHeaderMap);
      const tableData = convertTableDataToTabularData(tableResults?.[i]);
      const sort = decodeSorts(widget.queries[0]?.orderby)?.[0];

      return (
        <TableWrapper key={`table:${result.title}`}>
          {organization.features.includes('dashboards-use-widget-table-visualization') ? (
            <TableWidgetVisualization
              columns={columns}
              tableData={tableData}
              frameless
              scrollable
              fit="max-content"
              aliases={aliases}
              onChangeSort={onWidgetTableSort}
              sort={sort}
              getRenderer={(field, _dataRow, meta) => {
                const customRenderer = datasetConfig.getCustomFieldRenderer?.(
                  field,
                  meta as MetaType,
                  widget,
                  organization
                )!;

                return customRenderer;
              }}
              makeBaggage={(field, _dataRow, meta) => {
                const unit = meta.units?.[field] as string | undefined;

                return {
                  location,
                  organization,
                  theme,
                  unit,
                  eventView,
                } satisfies RenderFunctionBaggage;
              }}
              onResizeColumn={onWidgetTableResizeColumn}
              allowedCellActions={[]}
            />
          ) : (
            <StyledSimpleTableChart
              eventView={eventView}
              fieldAliases={fieldAliases}
              location={location}
              fields={fields}
              title={tableResults.length > 1 ? result.title : ''}
              // Bypass the loading state for span widgets because this renders the loading placeholder
              // and we want to show the underlying data during preflight instead
              loading={widget.widgetType === WidgetType.SPANS ? false : loading}
              loader={<LoadingPlaceholder />}
              metadata={result.meta}
              data={result.data}
              stickyHeaders
              fieldHeaderMap={datasetConfig.getFieldHeaderMap?.(widget.queries[i])}
              getCustomFieldRenderer={getCustomFieldRenderer}
              minColumnWidth={
                minTableColumnWidth ? minTableColumnWidth.toString() + 'px' : undefined
              }
            />
          )}
        </TableWrapper>
      );
    });
  }

  bigNumberComponent({loading, tableResults}: TableResultProps): React.ReactNode {
    if (typeof tableResults === 'undefined' || loading) {
      return <BigNumber>{'\u2014'}</BigNumber>;
    }

    const {widget} = this.props;

    return tableResults.map((result, i) => {
      const tableMeta = {...result.meta};
      const fields = Object.keys(tableMeta?.fields ?? {});

      let field = fields[0]!;
      let selectedField = field;

      if (defined(widget.queries[0]!.selectedAggregate)) {
        const index = widget.queries[0]!.selectedAggregate;
        selectedField = widget.queries[0]!.aggregates[index]!;
        if (fields.includes(selectedField)) {
          field = selectedField;
        }
      }

      const data = result?.data;
      const meta = result?.meta as EventsMetaType;
      const value = data?.[0]?.[selectedField];

      if (
        !field ||
        !result.data?.length ||
        selectedField === 'equation|' ||
        selectedField === '' ||
        !defined(value) ||
        !Number.isFinite(value) ||
        Number.isNaN(value)
      ) {
        return <BigNumber key={`big_number:${result.title}`}>{'\u2014'}</BigNumber>;
      }

      return (
        <BigNumberWidgetVisualization
          key={i}
          field={field}
          value={value}
          type={meta.fields?.[field] ?? null}
          unit={(meta.units?.[field] as DataUnit) ?? null}
          thresholds={widget.thresholds ?? undefined}
          preferredPolarity="-"
        />
      );
    });
  }

  chartRef: ReactEchartsRef | null = null;

  handleRef = (chartRef: ReactEchartsRef): void => {
    if (chartRef && !this.chartRef) {
      this.chartRef = chartRef;
      // add chart to the group so that it has synced cursors
      const instance = chartRef.getEchartsInstance?.();
      if (instance && !instance.group && this.props.chartGroup) {
        instance.group = this.props.chartGroup;
      }
    }

    if (!chartRef) {
      this.chartRef = null;
    }
  };

  chartComponent(chartProps: any): React.ReactNode {
    const {widget} = this.props;
    const stacked = widget.queries[0]?.columns.length! > 0;

    switch (widget.displayType) {
      case 'bar':
        return <BarChart {...chartProps} stacked={stacked} animation={false} />;
      case 'area':
      case 'top_n':
        return <AreaChart stacked {...chartProps} />;
      case 'line':
      default:
        return <LineChart {...chartProps} />;
    }
  }

  render() {
    const {
      theme,
      tableResults,
      timeseriesResults,
      errorMessage,
      loading,
      widget,
      onZoom,
      legendOptions,
      noPadding,
      timeseriesResultsTypes,
      shouldResize,
      confidence,
      showConfidenceWarning,
      sampleCount,
      isSampled,
      disableZoom,
      showLoadingText,
    } = this.props;

    if (errorMessage) {
      return (
        <StyledErrorPanel>
          <IconWarning color="gray500" size="lg" />
        </StyledErrorPanel>
      );
    }

    if (widget.displayType === 'table') {
      return getDynamicText({
        value: (
          <TransitionChart loading={loading} reloading={loading}>
            <LoadingScreen loading={loading} showLoadingText={showLoadingText} />
            {this.tableResultComponent({tableResults, loading})}
          </TransitionChart>
        ),
        fixed: <Placeholder height="200px" testId="skeleton-ui" />,
      });
    }

    if (widget.displayType === 'big_number') {
      return (
        <TransitionChart loading={loading} reloading={loading}>
          <LoadingScreen loading={loading} showLoadingText={showLoadingText} />
          <BigNumberResizeWrapper noPadding={noPadding}>
            {this.bigNumberComponent({tableResults, loading})}
          </BigNumberResizeWrapper>
        </TransitionChart>
      );
    }
    const {location, selection, onLegendSelectChanged, widgetLegendState} = this.props;
    const {start, end, period, utc} = selection.datetime;
    const {projects, environments} = selection;

    const otherRegex = new RegExp(`(?:.* : ${OTHER}$)|^${OTHER}$`);
    const shouldColorOther = timeseriesResults?.some(({seriesName}) =>
      seriesName?.match(otherRegex)
    );
    const colors = timeseriesResults
      ? (theme.chart
          .getColorPalette(timeseriesResults.length - (shouldColorOther ? 2 : 1))
          .slice() as string[])
      : [];
    // TODO(wmak): Need to change this when updating dashboards to support variable topEvents
    if (shouldColorOther) {
      colors[colors.length] = theme.chartOther;
    }

    // Create a list of series based on the order of the fields,
    const series = timeseriesResults
      ? timeseriesResults
          .map((values, i: number) => {
            let seriesName = '';
            if (values.seriesName !== undefined) {
              seriesName = isEquation(values.seriesName)
                ? getEquation(values.seriesName)
                : values.seriesName;
            }
            return {
              ...values,
              seriesName,
              fieldName: seriesName,
              color: colors[i],
            };
          })
          .filter(Boolean) // NOTE: `timeseriesResults` is a sparse array! We have to filter out the empty slots after the colors are assigned, since the colors are assigned based on sparse array index
      : [];

    const legend = {
      left: 0,
      top: 0,
      selected: getSeriesSelection(location),
      formatter: (seriesName: string) => {
        seriesName =
          WidgetLegendNameEncoderDecoder.decodeSeriesNameForLegend(seriesName)!;
        const arg = getAggregateArg(seriesName);
        if (arg !== null) {
          const slug = getMeasurementSlug(arg);
          if (slug !== null) {
            seriesName = slug.toUpperCase();
          }
        }
        if (maybeEquationAlias(seriesName)) {
          seriesName = stripEquationPrefix(seriesName);
        }
        return seriesName;
      },
      ...legendOptions,
    };

    const axisField = widget.queries[0]?.aggregates?.[0] ?? 'count()';
    const axisLabel = isEquation(axisField) ? getEquation(axisField) : axisField;

    // Check to see if all series output types are the same. If not, then default to number.
    const outputType =
      timeseriesResultsTypes && new Set(Object.values(timeseriesResultsTypes)).size === 1
        ? timeseriesResultsTypes[axisLabel]!
        : 'number';
    const isDurationChart = outputType === 'duration';
    const durationUnit = isDurationChart
      ? timeseriesResults && getDurationUnit(timeseriesResults, legendOptions)
      : undefined;
    const bucketSize = getBucketSize(timeseriesResults);

    const valueFormatter = (value: number, seriesName?: string) => {
      const decodedSeriesName = seriesName
        ? WidgetLegendNameEncoderDecoder.decodeSeriesNameForLegend(seriesName)
        : seriesName;
      const aggregateName = decodedSeriesName?.split(':').pop()?.trim();
      if (aggregateName) {
        return timeseriesResultsTypes
          ? tooltipFormatter(value, timeseriesResultsTypes[aggregateName])
          : tooltipFormatter(value, aggregateOutputType(aggregateName));
      }
      return tooltipFormatter(value, 'number');
    };

    const nameFormatter = (name: string) => {
      return WidgetLegendNameEncoderDecoder.decodeSeriesNameForLegend(name)!;
    };

    const chartOptions = {
      autoHeightResize: shouldResize ?? true,
      useMultilineDate: true,
      grid: {
        left: 0,
        right: 4,
        top: '40px',
        bottom: 0,
      },
      seriesOptions: {
        showSymbol: false,
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
        },
        formatter: (params: any, asyncTicket: any) => {
          const {chartGroup} = this.props;
          const isInGroup =
            chartGroup && chartGroup === this.chartRef?.getEchartsInstance().group;

          // tooltip is triggered whenever any chart in the group is hovered,
          // so we need to check if the mouse is actually over this chart
          if (isInGroup && !isChartHovered(this.chartRef)) {
            return '';
          }

          return getFormatter({
            valueFormatter,
            nameFormatter,
            isGroupedByDate: true,
            bucketSize,
            addSecondsToTimeFormat: false,
            showTimeInTooltip: true,
          })(params, asyncTicket);
        },
      },
      yAxis: {
        axisLabel: {
          color: theme.chartLabel,
          formatter: (value: number) => {
            if (timeseriesResultsTypes) {
              return axisLabelFormatterUsingAggregateOutputType(
                value,
                outputType,
                true,
                durationUnit,
                undefined,
                PERCENTAGE_DECIMAL_POINTS
              );
            }
            return axisLabelFormatter(
              value,
              aggregateOutputType(axisLabel),
              true,
              undefined,
              undefined,
              PERCENTAGE_DECIMAL_POINTS
            );
          },
        },
        axisPointer: {
          type: 'line',
          snap: false,
          lineStyle: {
            type: 'solid',
            width: 0.5,
          },
          label: {
            show: false,
          },
        },
        minInterval: durationUnit ?? 0,
      },
      xAxis: {
        axisPointer: {
          snap: true,
        },
      },
    };

    const ref = this.props.chartGroup ? this.handleRef : undefined;

    // Excluding Other uses a slightly altered regex to match the Other series name
    // because the series names are formatted with widget IDs to avoid conflicts
    // when deactivating them across widgets
    const topEventsCountExcludingOther =
      timeseriesResults?.length && widget.queries[0]?.columns.length
        ? Math.floor(timeseriesResults.length / widget.queries[0]?.aggregates.length) -
          (timeseriesResults?.some(
            ({seriesName}) =>
              shouldColorOther ||
              seriesName?.match(new RegExp(`(?:.* : ${OTHER};)|^${OTHER};`))
          )
            ? 1
            : 0)
        : undefined;
    return (
      <ChartZoom period={period} start={start} end={end} utc={utc} disabled={disableZoom}>
        {zoomRenderProps => {
          return (
            <ReleaseSeries
              end={end}
              start={start}
              period={period}
              environments={environments}
              projects={projects}
              memoized
              enabled={widgetLegendState.widgetRequiresLegendUnselection(widget)}
            >
              {({releaseSeries}) => {
                // make series name into seriesName:widgetId form for individual widget legend control
                // NOTE: e-charts legends control all charts that have the same series name so attaching
                // widget id will differentiate the charts allowing them to be controlled individually
                const modifiedReleaseSeriesResults =
                  WidgetLegendNameEncoderDecoder.modifyTimeseriesNames(
                    widget,
                    releaseSeries
                  );

                return (
                  <TransitionChart loading={loading} reloading={loading}>
                    <LoadingScreen loading={loading} showLoadingText={showLoadingText} />
                    <ChartWrapper
                      autoHeightResize={shouldResize ?? true}
                      noPadding={noPadding}
                    >
                      <RenderedChartContainer>
                        {getDynamicText({
                          value: this.chartComponent({
                            ...zoomRenderProps,
                            ...chartOptions,
                            // Override default datazoom behaviour for updating Global Selection Header
                            ...(onZoom ? {onDataZoom: onZoom} : {}),
                            legend,
                            series: [
                              ...series,
                              // only add release series if there is series data
                              ...(series?.length > 0
                                ? (modifiedReleaseSeriesResults ?? [])
                                : []),
                            ],
                            onLegendSelectChanged,
                            ref,
                          }),
                          fixed: <Placeholder height="200px" testId="skeleton-ui" />,
                        })}
                      </RenderedChartContainer>

                      {showConfidenceWarning && confidence && (
                        <ConfidenceFooter
                          confidence={confidence}
                          sampleCount={sampleCount}
                          topEvents={topEventsCountExcludingOther}
                          isSampled={isSampled}
                        />
                      )}
                    </ChartWrapper>
                  </TransitionChart>
                );
              }}
            </ReleaseSeries>
          );
        }}
      </ChartZoom>
    );
  }
}

export default withTheme(WidgetCardChart);

const StyledTransparentLoadingMask = styled((props: any) => (
  <TransparentLoadingMask {...props} maskBackgroundColor="transparent" />
))`
  display: flex;
  flex-direction: column;
  gap: ${space(2)};
  justify-content: center;
  align-items: center;
  pointer-events: none;
`;

function LoadingScreen({
  loading,
  showLoadingText,
}: {
  loading: boolean;
  showLoadingText?: boolean;
}) {
  if (!loading) {
    return null;
  }

  return (
    <StyledTransparentLoadingMask visible={loading}>
      <LoadingIndicator mini />
      {showLoadingText && (
        <p id="loading-text">{t('Turning data into pixels - almost ready')}</p>
      )}
    </StyledTransparentLoadingMask>
  );
}

const LoadingPlaceholder = styled(({className}: PlaceholderProps) => (
  <Placeholder height="200px" className={className} />
))`
  background-color: ${p => p.theme.surface300};
`;

const BigNumberResizeWrapper = styled('div')<{noPadding?: boolean}>`
  flex-grow: 1;
  overflow: hidden;
  position: relative;
  padding: ${p =>
    p.noPadding ? `0` : `0${space(1)} ${space(3)} ${space(3)} ${space(3)}`};
`;

const BigNumber = styled('div')`
  line-height: 1;
  display: inline-flex;
  flex: 1;
  width: 100%;
  min-height: 0;
  font-size: 32px;
  color: ${p => p.theme.headingColor};

  * {
    text-align: left !important;
  }
`;

const ChartWrapper = styled('div')<{autoHeightResize: boolean; noPadding?: boolean}>`
  ${p => p.autoHeightResize && 'height: 100%;'}
  width: 100%;
  padding: ${p => (p.noPadding ? `0` : `0 ${space(2)} ${space(2)}`)};
  display: flex;
  flex-direction: column;
  gap: ${space(1)};
`;

const TableWrapper = styled('div')`
  margin-top: ${space(1.5)};
  min-height: 0;
  border-bottom-left-radius: ${p => p.theme.borderRadius};
  border-bottom-right-radius: ${p => p.theme.borderRadius};
`;

const StyledSimpleTableChart = styled(SimpleTableChart)`
  overflow: auto;
  height: 100%;
`;

const StyledErrorPanel = styled(ErrorPanel)`
  padding: ${space(2)};
`;

const RenderedChartContainer = styled('div')`
  flex: 1;
`;
