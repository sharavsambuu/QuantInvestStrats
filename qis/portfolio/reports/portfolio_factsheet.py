"""
generate portfolio factsheet report using PortfolioData data object
with comparision to 1-2 cash benchmarks
"""
# built in
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Union, Optional, Tuple, Literal
from enum import Enum

# qis
import qis.file_utils as fu
import qis.utils.struct_ops as sop
import qis.utils.dates as da
from qis.utils.dates import TimePeriod
from qis.perfstats.config import PerfParams
import qis.perfstats.drawdowns as cdr
import qis.perfstats.regime_classifier as rcl
from qis.perfstats.regime_classifier import BenchmarkReturnsQuantileRegimeSpecs

# plots
import qis.plots.utils as put
import qis.plots.derived.prices as ppd
import qis.plots.time_series as pts
import qis.plots.stackplot as pst

# portfolio
import qis.portfolio.backtester as bp
from qis.portfolio.portfolio_data import PortfolioData, AttributionMetric


PERF_PARAMS = PerfParams(freq='W-WED')
REGIME_PARAMS = BenchmarkReturnsQuantileRegimeSpecs(freq='Q')

FIG_SIZE = (8.3, 11.7)  # A4 for portrait

# use for number years > 5
KWARG_LONG = dict(perf_params=PerfParams(freq='W-WED', freq_reg='Q'),
                  regime_params=BenchmarkReturnsQuantileRegimeSpecs(freq='Q'),
                  x_date_freq='A',
                  date_format='%b-%y')

# use for number years < 3
KWARG_SHORT = dict(perf_params=PerfParams(freq='W-WED', freq_reg='M'),
                   regime_params=BenchmarkReturnsQuantileRegimeSpecs(freq='M'),
                   x_date_freq='Q',
                   date_format='%b-%y')


def generate_portfolio_factsheet(portfolio_data: PortfolioData,
                                 benchmark_prices: pd.DataFrame,
                                 time_period: TimePeriod = None,
                                 perf_params: PerfParams = PERF_PARAMS,
                                 regime_params: BenchmarkReturnsQuantileRegimeSpecs = REGIME_PARAMS,
                                 file_name_to_save: str = None,
                                 **kwargs
                                 ) -> plt.Figure:
    # align
    benchmark_prices = benchmark_prices.reindex(index=portfolio_data.nav.index, method='ffill')
    regime_benchmark = benchmark_prices.columns[0]

    fig = plt.figure(figsize=FIG_SIZE, constrained_layout=True)
    gs = fig.add_gridspec(nrows=14, ncols=4, wspace=0.0, hspace=0.0)

    plot_kwargs = dict(fontsize=5,
                       linewidth=0.5,
                       digits_to_show=1, sharpe_digits=2,
                       weight='normal',
                       markersize=1,
                       legend_alpha=0.75)
    kwargs = sop.update_kwargs(kwargs, plot_kwargs)
    fig.suptitle(f"{portfolio_data.nav.name} portfolio factsheet",
                 fontweight="bold", fontsize=8, color='blue')

    # prices
    joint_prices = pd.concat([portfolio_data.get_portfolio_nav(time_period=time_period), benchmark_prices], axis=1).dropna()
    pivot_prices = joint_prices[regime_benchmark]
    ax = fig.add_subplot(gs[0:2, :2])
    ppd.plot_prices(prices=joint_prices,
                    perf_params=perf_params,
                    title='Performance',
                    ax=ax,
                    **kwargs)
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # dd
    ax = fig.add_subplot(gs[2:4, :2])
    cdr.plot_drawdown(prices=joint_prices,
                      title='Running Drawdowns',
                      dd_legend_type=cdr.DdLegendType.SIMPLE,
                      ax=ax, **kwargs)
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # exposures
    if len(portfolio_data.weights.columns) > 10:
        exposures = portfolio_data.get_exposures(is_grouped=True, time_period=time_period)
    else:
        exposures = portfolio_data.get_exposures(is_grouped=False, time_period=time_period)
    ax = fig.add_subplot(gs[4:6, :2])
    pst.stackplot_timeseries(df=exposures.resample('W-WED').last(),
                             is_add_mean_levels=False,
                             is_use_bar_plot=True,
                             baseline='zero',
                             title='Exposures',
                             legend_line_type=pst.LegendLineType.AVG_LAST,
                             var_format='{:.1%}',
                             ax=ax,
                             **sop.update_kwargs(kwargs,
                                                 dict(bbox_to_anchor=(0.5, 1.05), ncol=2)))
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # turnover
    ax = fig.add_subplot(gs[6:8, :2])
    turnover = portfolio_data.get_turnover(time_period=time_period, roll_period=260)

    pts.plot_time_series(df=turnover,
                         var_format='{:,.2%}',
                         # y_limits=(0.0, None),
                         legend_line_type=pts.LegendLineType.AVG_LAST,
                         title='1y rolling average Turnover',
                         ax=ax,
                         **kwargs)
    """
    pts.plot_time_series_2ax(df1=turnover.drop(portfolio_data.nav.name, axis=1),
                             df2=turnover[portfolio_data.nav.name],
                             var_format='{:,.2%}',
                             # y_limits=(0.0, None),
                             legend_line_type=pts.LegendLineType.AVG_LAST,
                             title='1y rolling average Turnover',
                             ax=ax,
                             **kwargs)
    """
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)
    
    # benchmark betas
    ax = fig.add_subplot(gs[8:10, :2])
    factor_exposures = portfolio_data.compute_portfolio_benchmark_betas(benchmark_prices=benchmark_prices,
                                                                        time_period=time_period)
    pts.plot_time_series(df=factor_exposures,
                         var_format='{:,.2f}',
                         # y_limits=(0.0, None),
                         legend_line_type=pts.LegendLineType.FIRST_LAST,
                         title='Portfolio Benchmark betas',
                         ax=ax,
                         **kwargs)
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # attribution
    ax = fig.add_subplot(gs[10:12, :2])
    factor_attribution = portfolio_data.compute_portfolio_benchmark_attribution(benchmark_prices=benchmark_prices,
                                                                                time_period=time_period)
    pts.plot_time_series(df=factor_attribution,
                         var_format='{:,.0%}',
                         # y_limits=(0.0, None),
                         legend_line_type=pts.LegendLineType.LAST,
                         title='Portfolio Cumulative return attribution to benchmark betas',
                         ax=ax,
                         **kwargs)
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # constituents
    ax = fig.add_subplot(gs[12:, :2])
    num_investable_instruments=portfolio_data.get_num_investable_instruments(time_period=time_period)
    pts.plot_time_series(df=num_investable_instruments,
                         var_format='{:,.0f}',
                         legend_line_type=pts.LegendLineType.FIRST_AVG_LAST,
                         title='Number of investable instruments',
                         ax=ax,
                         **kwargs)
    rcl.add_bnb_regime_shadows(ax=ax, pivot_prices=pivot_prices, regime_params=regime_params)
    put.set_spines(ax=ax, bottom_spine=False, left_spine=False)

    # ra perf table
    ax = fig.add_subplot(gs[0, 2:])
    portfolio_data.plot_ra_perf_table(ax=ax,
                                      benchmark_price=benchmark_prices.iloc[:, 0],
                                      time_period=time_period,
                                      perf_params=perf_params,
                                      **sop.update_kwargs(kwargs, dict(fontsize=4)))
    ax = fig.add_subplot(gs[1, 2:])
    portfolio_data.plot_ra_perf_table(ax=ax,
                                      benchmark_price=benchmark_prices.iloc[:, 0],
                                      time_period=da.get_time_period_shifted_by_years(time_period=time_period),
                                      perf_params=perf_params,
                                      **sop.update_kwargs(kwargs, dict(fontsize=4)))

    # heatmap
    ax = fig.add_subplot(gs[2:4, 2:])
    portfolio_data.plot_monthly_returns_heatmap(ax=ax,
                                                time_period=time_period,
                                                title='Monthly Returns',
                                                **sop.update_kwargs(kwargs, dict(fontsize=4)))

    # periodic returns
    ax = fig.add_subplot(gs[4:6, 2:])
    local_kwargs = sop.update_kwargs(kwargs=kwargs,
                                     new_kwargs=dict(fontsize=4, square=False, x_rotation=90, is_transpose=True))
    portfolio_data.plot_periodic_returns(ax=ax,
                                         benchmark_prices=benchmark_prices,
                                         heatmap_freq='A',
                                         time_period=time_period,
                                         **sop.update_kwargs(local_kwargs, dict(date_format='%Y')))

    # perf contributors
    ax = fig.add_subplot(gs[6:8, 2])
    portfolio_data.plot_contributors(ax=ax,
                                     time_period=time_period,
                                     title=f"Performance Contributors {time_period.to_str()}",
                                     **kwargs)

    ax = fig.add_subplot(gs[6:8, 3])
    time_period_1y = da.get_time_period_shifted_by_years(time_period=time_period)
    portfolio_data.plot_contributors(ax=ax,
                                     time_period=time_period_1y,
                                     title=f"Performance Contributors {time_period_1y.to_str()}",
                                     **kwargs)

    # regime data
    ax = fig.add_subplot(gs[8:10, 2:])
    portfolio_data.plot_regime_data(ax=ax,
                                    benchmark_price=benchmark_prices.iloc[:, 0],
                                    time_period=time_period,
                                    perf_params=perf_params,
                                    regime_params=regime_params,
                                    **kwargs)

    # vol regime data
    """
    ax = fig.add_subplot(gs[10:12, 2:])
    portfolio_data.plot_vol_regimes(ax=ax,
                                    benchmark_price=benchmark_prices.iloc[:, 0],
                                    time_period=time_period,
                                    perf_params=perf_params,
                                    regime_params=regime_params,
                                    **kwargs)
    """
    # returns scatter
    ax = fig.add_subplot(gs[10:12, 2:])
    portfolio_data.plot_returns_scatter(ax=ax,
                                        benchmark_price=benchmark_prices.iloc[:, 0],
                                        time_period=time_period,
                                        freq=perf_params.freq_reg,
                                        **kwargs)

    if len(benchmark_prices.columns) > 1:
        ax = fig.add_subplot(gs[12:, 2:])
        portfolio_data.plot_returns_scatter(ax=ax,
                                            benchmark_price=benchmark_prices.iloc[:, 1],
                                            time_period=time_period,
                                            **kwargs)

    if file_name_to_save is not None:
        fu.figs_to_pdf(figs=[fig], file_name=file_name_to_save, orientation='landscape')
    return fig


class UnitTests(Enum):
    TEST1 = 1
    TEST2 = 2


def run_unit_test(unit_test: UnitTests):

    from qis.data.yf_data import load_etf_data
    prices = load_etf_data()#.dropna()
    time_period = TimePeriod('31Dec2001', '31Dec2022')
    prices = time_period.locate(prices)
    group_data = pd.Series(dict(SPY='Equities', QQQ='Equities', EEM='Equities', TLT='Bonds', IEF='Bonds', SHY='Bonds', LQD='Credit', HYG='HighYield', GLD='Gold'))

    benchmark_prices = prices[['SPY', 'TLT']]

    portfolio_data = bp.backtest_model_portfolio(prices=prices,
                                                 weights=np.ones(len(prices.columns)) / len(prices.columns),
                                                 is_output_portfolio_data=True,
                                                 ticker='EqualWeighted')
    portfolio_data._set_group_data(group_data=group_data, group_order=list(group_data.unique()))

    if unit_test == UnitTests.TEST1:
        generate_portfolio_factsheet(portfolio_data=portfolio_data,
                                     benchmark_prices=benchmark_prices,
                                     time_period=TimePeriod('31Dec2005', '31Dec2022'),
                                     file_name_to_save=f"{portfolio_data.nav.name}_portfolio_factsheet",
                                     **KWARG_LONG)

    if unit_test == UnitTests.TEST2:
        generate_portfolio_factsheet(portfolio_data=portfolio_data,
                                     benchmark_prices=benchmark_prices,
                                     time_period=TimePeriod('31Dec2019', '31Dec2022'),
                                     file_name_to_save=f"{portfolio_data.nav.name}_portfolio_factsheet",
                                     **KWARG_SHORT)

    plt.show()


if __name__ == '__main__':

    unit_test = UnitTests.TEST1

    is_run_all_tests = False
    if is_run_all_tests:
        for unit_test in UnitTests:
            run_unit_test(unit_test=unit_test)
    else:
        run_unit_test(unit_test=unit_test)