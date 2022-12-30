"""
core for computing performance
"""
# built in
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from enum import Enum
from typing import Union, Dict, Optional

# qis
import qis.utils.dates as da
import qis.utils.df_ops as dfo
import qis.utils.np_ops as npo
import qis.utils.df_freq as dff
from qis.utils.dates import CALENDAR_DAYS_PER_YEAR_SHARPE
from qis.perfstats.config import PerfStat, ReturnTypes, PerfParams


def compute_num_years(prices: Union[pd.DataFrame, pd.Series],
                      days_per_year: float = CALENDAR_DAYS_PER_YEAR_SHARPE
                      ) -> float:
    return (prices.index[-1] - prices.index[0]).days / days_per_year


def to_returns(prices: Union[pd.Series, pd.DataFrame],
               is_log_returns: bool = False,
               return_type: ReturnTypes = ReturnTypes.RELATIVE,
               freq: Optional[str] = None,
               include_start_date: bool = False,
               include_end_date: bool = False,
               ffill_nans: bool = True,
               drop_first: bool = False,
               is_first_zero: bool = False,
               **kwargs
               ) -> Union[pd.Series, pd.DataFrame]:
    """
    compute periodic returns using return_type
    """
    prices = prices_at_freq(prices=prices, freq=freq,
                            include_start_date=include_start_date,
                            include_end_date=include_end_date,
                            ffill_nans=ffill_nans)

    ind_good = np.logical_and(
        np.logical_and(np.isnan(prices)==False, np.isnan(prices)==False),
        np.logical_and(np.greater(prices, 0.0), np.greater(prices, 0.0)))

    if return_type == ReturnTypes.LOG or is_log_returns:
        returns = np.log(np.divide(prices, prices.shift(1)), where=ind_good)
    elif return_type == ReturnTypes.RELATIVE:
        returns = np.divide(prices, prices.shift(1), where=ind_good).add(-1.0)

    elif return_type == ReturnTypes.DIFFERENCE:
        returns = prices - prices.shift(1)

    elif return_type == ReturnTypes.LEVEL:
        returns = prices

    elif return_type == ReturnTypes.LEVEL0:
        returns = prices.shift(1)
    else:
        raise NotImplementedError (f"{return_type}")

    if is_first_zero:
        returns = set_zero_first(returns=returns)
    elif drop_first:
        returns = drop_first_row(returns=returns)

    return returns


def to_total_returns(prices: Union[pd.Series, pd.DataFrame]) -> pd.Series:
    total_returns = compute_total_return(prices=prices)
    if isinstance(prices, pd.DataFrame):
        total_returns = pd.Series(total_returns, index=prices.columns)
    elif isinstance(prices, pd.Series):
        total_returns = pd.Series(total_returns, name=prices.name)
    else:
        raise NotImplementedError(f"{type(prices)}")

    return total_returns


def compute_total_return(prices: Union[pd.DataFrame, pd.Series]) -> Union[np.ndarray, float]:
    """
    np.ndarray for pd.DataFrame
    float for pd.Series
    """
    if len(prices.index) == 1:
        if isinstance(prices, pd.DataFrame):
            return np.full(len(prices.columns), fill_value=np.nan)
        elif isinstance(prices, pd.Series):
            return np.nan
        else:
            raise TypeError(f"unsuported type={type(prices)}")

    if isinstance(prices, pd.DataFrame):
        price_0 = prices.iloc[0, :].to_numpy()
        if np.any(np.isnan(price_0)):
            price_0 = dfo.get_first_non_nan_values(df=prices)
            print(f"detected nan price for prices = {prices.iloc[0, :]},"
                  f" using first non nan price = {price_0} for {prices.columns}")

        price_end = prices.iloc[-1, :].to_numpy()

    elif isinstance(prices, pd.Series):
        price_0 = prices.iloc[0]
        if np.isnan(price_0):
            price_0 = dfo.get_first_non_nan_values(df=prices)
            print(f"detected nan price for prices = {prices.iloc[0]},"
                  f" using first non nan price = {price_0} for {prices.name}")

        price_end = prices[-1]

    else:
        raise TypeError(f"unsuported type={type(prices)}")

    num_years = compute_num_years(prices=prices)
    if num_years > 0.0:
        total_return = price_end / price_0 - 1.0
    else:
        print(prices)
        print(f"total return has incosistent dates t0={prices.index[0]} and t1={prices.index[-1]}")
        total_return = np.full(len(prices.columns), fill_value=np.nan) if isinstance(prices, pd.DataFrame) else np.nan
    return total_return


def compute_pa_return(prices: Union[pd.DataFrame, pd.Series],
                      annualize_less_1y: bool = False
                      ) -> Union[np.ndarray, float]:
    """
    np.ndarray for pd.DataFrame
    float for pd.Series
    """
    total_return = compute_total_return(prices=prices)
    num_years = compute_num_years(prices=prices)

    if num_years > 0.0:
        ratio = total_return + 1.0

        if num_years > 1.0:
            compounded_return_pa = ratio ** (1.0 / num_years) - 1
        else:
            if annualize_less_1y:  # annualize to 1y, not compound
                compounded_return_pa = total_return / num_years
            else:  # use ytd return
                compounded_return_pa = ratio - 1.0
    else:
        n = len(prices.columns) if isinstance(prices, pd.DataFrame) else 1
        compounded_return_pa = np.zeros_like(n)

    return compounded_return_pa


def compute_returns_dict(prices: Union[pd.DataFrame, pd.Series],
                         perf_params: PerfParams = None,
                         annualize_less_1y: bool = False
                         ) -> Dict[str, np.ndarray]:
    """
    compute returns for one asset
    """
    if prices.empty:
        print(f"in compute_pa_return_dict: {prices} is all nans")
        n = len(prices.columns) if isinstance(prices, pd.DataFrame) else 1
        return_dict = {PerfStat.TOTAL_RETURN.to_str(): np.full(n, fill_value=np.nan),
                       PerfStat.PA_RETURN.to_str(): np.full(n, fill_value=np.nan),
                       PerfStat.AN_LOG_RETURN.to_str(): np.full(n, fill_value=np.nan),
                       PerfStat.AVG_AN_RETURN.to_str(): np.full(n, fill_value=np.nan),
                       PerfStat.NUM_YEARS.to_str(): np.full(n, fill_value=np.nan)}
        return return_dict

    if perf_params is None:  # only needed for EXCESS returns use defaults
        perf_params = PerfParams()

    compounded_return_pa = compute_pa_return(prices=prices, annualize_less_1y=annualize_less_1y)
    total_return = compute_total_return(prices=prices)
    num_years = compute_num_years(prices=prices)

    if perf_params.rates_data is not None:
        excess_return = compute_pa_excess_returns(returns=to_returns(prices),
                                                  rates_data=perf_params.rates_data,
                                                  first_date=prices.index[0],
                                                  annualize_less_1y=annualize_less_1y)
    else:
        excess_return = compounded_return_pa

    if isinstance(prices, pd.DataFrame):
        start_value = prices.iloc[0, :].to_numpy()
        end_value = prices.iloc[-1, :].to_numpy()
    else:
        start_value = prices.iloc[0]
        end_value = prices.iloc[-1]

    # make dictionary output
    return_dict = {PerfStat.TOTAL_RETURN.to_str(): total_return,
                   PerfStat.PA_RETURN.to_str(): compounded_return_pa,
                   PerfStat.PA_EXCESS_RETURN.to_str(): excess_return,
                   PerfStat.AN_LOG_RETURN.to_str(): np.log(1.0 + compounded_return_pa),
                   PerfStat.AVG_AN_RETURN.to_str(): np.divide(total_return, num_years),
                   PerfStat.NAV1.to_str(): (1.0+total_return),
                   PerfStat.NUM_YEARS.to_str(): num_years,
                   PerfStat.START_DATE.to_str(): prices.index[0]}

    return_dict[PerfStat.START_DATE.to_str()] = prices.index[0]
    return_dict[PerfStat.END_DATE.to_str()] = prices.index[-1]
    return_dict[PerfStat.START_PRICE.to_str()] = start_value
    return_dict[PerfStat.END_PRICE.to_str()] = end_value

    return return_dict


def compute_excess_returns(returns: Union[pd.Series, pd.DataFrame],
                           rates_data: pd.Series
                           ) -> Union[pd.Series, pd.DataFrame]:
    # get returns and subtract average rate between dt times:
    rates_dt = dfo.multiply_df_by_dt(df=rates_data, dates=returns.index, lag=None)
    if isinstance(returns, pd.Series):
        returns = returns.to_frame(name=returns.name)
    excess_returns = returns.subtract(rates_dt.to_numpy(), axis=0)
    if isinstance(returns, pd.Series):
        excess_returns = excess_returns.iloc[:, 0]
    return excess_returns


def compute_pa_excess_returns(returns: Union[pd.Series, pd.DataFrame],
                              rates_data: pd.Series,
                              first_date: pd.Timestamp = None,
                              annualize_less_1y: bool = False
                              ) -> Union[np.ndarray, float]:
    excess_returns = compute_excess_returns(returns=returns, rates_data=rates_data)
    prices = create_nav_from_returns(returns=excess_returns, first_date=first_date)
    compounded_return_pa = compute_pa_return(prices=prices, annualize_less_1y=annualize_less_1y)
    if isinstance(returns, pd.Series):
        compounded_return_pa = compounded_return_pa[0]
    return compounded_return_pa


def estimate_vol(sampled_returns: Union[pd.DataFrame, pd.Series, np.ndarray]) -> np.ndarray:
    if isinstance(sampled_returns, np.ndarray):
        n = sampled_returns.shape[0]
    else:
        n = len(sampled_returns.index)
    if n >= 20:  # adjust for mean for small sample
        vol = np.nanstd(sampled_returns, axis=0, ddof=1)
    else: # take sum
        vol = np.sqrt(np.nanmean(np.power(sampled_returns, 2), axis=0))
    return vol


def compute_sampled_vols(prices: Union[pd.DataFrame, pd.Series],
                         freq_vol: str = 'M',
                         freq_return: Optional[str] = None,
                         include_start_date: bool = False,
                         include_end_date: bool = False,
                         ) -> Union[pd.DataFrame, pd.Series]:

    """
    compute close to close vol based on return samples
    """
    sampled_returns = to_returns(prices=prices, freq=freq_return,
                                 include_start_date=include_start_date, include_end_date=include_end_date)
    # sampled_returns_at_vol_freq = sampled_returns.resample(freq_vol)
    sampled_returns_at_vol_freq = da.split_df_by_freq(df=sampled_returns,
                                                      freq=freq_vol,
                                                      overlap_frequency=None,
                                                      include_start_date=include_start_date,
                                                      include_end_date=include_end_date)

    vol_samples = {}
    for key, df in sampled_returns_at_vol_freq.items():
        vol_samples[key] = estimate_vol(sampled_returns=df.to_numpy())

    if isinstance(prices, pd.Series):
        vols = pd.DataFrame.from_dict(vol_samples, orient='index').iloc[:, 0].rename(prices.name)
    else:
        vols = pd.DataFrame.from_dict(vol_samples, orient='index', columns=prices.columns)
    vols = vols.multiply(np.sqrt(da.infer_an_from_data(sampled_returns)))

    return vols


def portfolio_navs_to_additive(grouped_nav: pd.DataFrame,
                               portfolio_name: str
                               ) -> pd.DataFrame:
    """
    given pandas with portfolio total and asset navs adjust asset navs
    """
    portfolio_nav = grouped_nav[portfolio_name]
    ac_nav_adj = adjust_navs_to_portfolio_pa(portfolio_nav=portfolio_nav,
                                             asset_prices=grouped_nav.drop(columns=[portfolio_name]))
    grouped_nav = pd.concat([portfolio_nav, ac_nav_adj], axis=1)
    return grouped_nav


def adjust_navs_to_portfolio_pa(portfolio_nav: pd.Series,
                                asset_prices: pd.DataFrame
                                ) -> pd.DataFrame:
    """
    adjust navs of portfolio navs so that the total pa return on navs are additive to portfolio total
    adjustment to match terminal value backpropagated: more stable
    """
    portfolio_pa = compute_pa_return(prices=portfolio_nav)
    assets_pa = compute_pa_return(prices=asset_prices)
    n = len(asset_prices.columns)
    asset_prices_adj = asset_prices.copy()
    t = (portfolio_nav.index - portfolio_nav.index[0]).days.to_numpy() / CALENDAR_DAYS_PER_YEAR_SHARPE
    c_m = ((portfolio_pa / n + 1.0) / (np.nanmean(assets_pa) + 1.0)) ** t
    ratio = npo.np_array_to_df_columns(a=c_m, n_col=n)
    asset_prices_adj = asset_prices_adj.multiply(ratio)
    asset_prices_adj = asset_prices_adj[asset_prices.columns]
    return asset_prices_adj


def compute_net_return(gross_return: pd.Series,
                       man_fee: float = 0.01,
                       perf_fee: float = 0.2,
                       perf_fee_frequency: str = 'A'
                       ) -> pd.Series:
    """
    compute fee adjusted returns from gross returns
    """
    perf_fee_cristalization_schedule = da.generate_dates_schedule(time_period=da.TimePeriod(gross_return.index[0], gross_return.index[-1]),
                                                                  freq=perf_fee_frequency)

    perf_cris_dates = np.isin(element=gross_return.index,
                              test_elements=perf_fee_cristalization_schedule,
                              assume_unique=True)

    nav_data = pd.DataFrame(data=0,
                            index=gross_return.index,
                            columns=['Net Return', 'NAV', 'GAV', 'PF', 'HWM', 'CPF'])
    nav_data.insert(loc=0, column='gross return', value=gross_return.to_numpy())
    nav_data = nav_data.copy()

    nav_data.loc[nav_data.index[0], 'GAV'] = 100.0
    nav_data.loc[nav_data.index[0], 'NAV'] = 100.0
    nav_data.loc[nav_data.index[0], 'HWM'] = 100.0

    for date, last_date, perf_cris_date in zip(nav_data.index[1:], nav_data.index[0:], perf_cris_dates[1:]):

        man_fee_dt = man_fee * (date-last_date).days/365.0

        nav_data.loc[date, 'GAV'] = (1.0+nav_data.loc[date, 'gross return']-man_fee_dt)*nav_data.loc[last_date, 'GAV']

        nav_data.loc[date, 'PF'] = perf_fee*np.maximum(nav_data.loc[date, 'GAV']-nav_data.loc[last_date, 'HWM'], 0.0)
        nav_data.loc[date, 'NAV'] = nav_data.loc[date, 'GAV']-nav_data.loc[date, 'PF']
        nav_data.loc[date, 'HWM'] = nav_data.loc[last_date, 'HWM']

        if perf_cris_date:
            nav_data.loc[date, 'CPF'] = nav_data.loc[date, 'PF']
            nav_data.loc[date, 'HWM'] = np.maximum(nav_data.loc[date, 'NAV'], nav_data.loc[last_date, 'HWM'] )
            nav_data.loc[date, 'GAV'] = nav_data.loc[date, 'GAV'] - nav_data.loc[date, 'CPF']

    net_return = nav_data['NAV'] / nav_data['NAV'].shift(1)-1.0
    net_return = net_return.copy()
    net_return.iloc[0] = 0.0
    net_return = net_return.rename(gross_return.name)

    return net_return


def get_net_navs(navs: Union[pd.Series, pd.DataFrame],
                 man_fee: float = 0.01,
                 perf_fee: float = 0.2,
                 perf_fee_frequency: str = 'A'
                 ) -> Union[pd.Series, pd.DataFrame]:

    gross_returns = navs.pct_change()
    net_returns = []
    if isinstance(navs, pd.Series):
        net_returns = compute_net_return(gross_return=gross_returns,
                                         man_fee=man_fee,
                                         perf_fee=perf_fee,
                                         perf_fee_frequency=perf_fee_frequency)
    else:
        for column in gross_returns.columns:
            net = compute_net_return(gross_return=gross_returns[column],
                                     man_fee=man_fee,
                                     perf_fee=perf_fee,
                                     perf_fee_frequency=perf_fee_frequency)
            net_returns.append(net)
        net_returns = pd.concat(net_returns, axis=1)
    net_nav = returns_to_nav(returns=net_returns)
    return net_nav


def returns_to_nav(returns: Union[pd.Series, pd.DataFrame],
                   init_period: Optional[int] = 1,
                   terminal_value: np.ndarray = None,
                   init_value: Union[np.ndarray, float] = None,
                   freq: Optional[str] = None,
                   constant_trade_level: bool = False
                   ) -> Union[pd.Series, pd.DataFrame]:
    """
    instrument returns to nav
    init_period of one by default will exlude the first day of returns for compunded nav
    """
    if init_period is not None and isinstance(returns, np.ndarray) is False:
        returns = to_zero_first_non_nan_returns(returns=returns, init_period=init_period)

    if constant_trade_level:
        strategy_nav = returns.cumsum(skipna=True, axis=0).add(1.0)
    else:
        if isinstance(returns, np.ndarray):
            strategy_nav = np.cumprod(1.0+returns, axis=0)
        else:
            strategy_nav = returns.add(1.0).cumprod(skipna=True)

    if terminal_value is not None:
        terminal_value_last = dfo.get_last_non_nan_values(strategy_nav)
        strategy_nav = strategy_nav.multiply(terminal_value/terminal_value_last)
    elif init_value is not None:
        initial_value_first = dfo.get_first_non_nan_values(df=strategy_nav)
        strategy_nav = strategy_nav.multiply(init_value / initial_value_first)

    if freq is not None:  # when it is important to have fixed frequency ffill prices
        strategy_nav = strategy_nav.asfreq(freq, method='ffill').fillna(method='ffill')

    return strategy_nav


def to_scaled_nav(prices: Union[pd.Series, pd.DataFrame], scale=0.5):
    returns = scale * to_returns(prices=prices, is_log_returns=False, is_first_zero=True)
    navs = returns_to_nav(returns=returns)
    return navs


def prices_at_freq(prices: Union[pd.Series, pd.DataFrame],
                   freq: Optional[str] = None,
                   include_start_date: bool = False,
                   include_end_date: bool = False,
                   ffill_nans: bool = True
                   ) -> Union[pd.Series, pd.DataFrame]:
    """
    get prices at freq
    """
    if ffill_nans:
        method = 'ffill'
    else:
        method = None
    if freq is not None:
        prices = dff.df_asfreq(df=prices,
                               freq=freq,
                               include_start_date=include_start_date,
                               include_end_date=include_end_date,
                               method=method)
    else:
        if method is not None:
            prices = prices.fillna(method=method)
    return prices


def log_returns_to_nav(log_returns: Union[np.ndarray, pd.Series, pd.DataFrame],
                       init_period: Optional[int] = None,
                       terminal_value: np.ndarray = None,
                       init_value: Union[np.ndarray, float] = None
                       ) -> Union[pd.Series, pd.DataFrame]:
    """
    instrument returns to nav
    init_period of one by default will exlude the first day of returns for compunded nav
    """
    if init_period is not None and isinstance(log_returns, np.ndarray) is False:
        log_returns = to_zero_first_non_nan_returns(returns=log_returns, init_period=init_period)

    strategy_nav = np.exp(log_returns.cumsum(axis=0, skipna=True))

    if terminal_value is not None:
        strategy_nav = strategy_nav.multiply(terminal_value/strategy_nav.iloc[-1])
    elif init_value is not None:
        strategy_nav = strategy_nav.divide(dfo.get_first_non_nan_values(df=strategy_nav) / init_value)

    return strategy_nav


def to_relative_nav(price1: pd.Series, price2: pd.Series) -> pd.Series:
    returns = to_returns(pd.concat([price1, price2], axis=1).fillna(method='ffill'), is_first_zero=True)
    relative_returns = np.subtract(returns[price1.name], returns[price2.name])
    relative_nav = returns_to_nav(returns=relative_returns, init_period=1)
    return relative_nav


def drop_first_row(returns: Union[pd.Series, pd.DataFrame]) -> Union[pd.Series, pd.DataFrame]:
    if isinstance(returns, pd.DataFrame):
        returns = returns.iloc[1:, :]
    else:
        returns = returns.iloc[1:]
    return returns


def set_zero_first(returns: Union[pd.Series, pd.DataFrame]) -> Union[pd.Series, pd.DataFrame]:
    if isinstance(returns, pd.DataFrame):
        returns.iloc[0, :] = 0
    else:
        returns.iloc[0] = 0
    return returns


def to_portfolio_returns(weights: pd.DataFrame,
                         returns: pd.DataFrame,
                         portfolio_name: str = 'portfolios'
                         ) -> pd.Series:
    """
    instrument returns to portfolio, equivalent to with
    portfolio_returns = returns.multiply(weights.shift(1)).sum(axis=1)
    but with handling of nan instead of zero when using .sum(axis=1)
    """
    weights_1 = weights.shift(1)
    portfolio_pnl = returns.multiply(weights_1).to_numpy()
    pnl = np.nansum(portfolio_pnl, axis=1)
    is_all_nan = np.all(np.isnan(portfolio_pnl), axis=1)
    portfolio_pnl = np.where(is_all_nan, np.nan, pnl)
    portfolio_returns = pd.Series(data=portfolio_pnl,
                                  index=returns.index,
                                  name=portfolio_name)
    return portfolio_returns


def portfolio_returns_to_nav(returns: pd.DataFrame,
                             init_period: Optional[int] = 1,
                             init_value: Union[np.ndarray, float] = None,
                             freq: Optional[str] = None
                             ) -> Union[pd.Series, pd.DataFrame]:
    """
    instrument returns to nav
    """

    agg_pnl = pd.Series(np.nansum(returns.to_numpy(), axis=1), index=returns.index)
    nav = returns_to_nav(returns=agg_pnl, init_period=init_period, init_value=init_value, freq=freq)
    return nav


def compute_grouped_nav(returns: pd.DataFrame,
                        init_period: Union[int, None] = None,
                        init_value: float = 1.0,
                        freq: Optional[str] = None
                        ) -> pd.Series:
    """
    use implementation returns_to_nav()
    """
    grouped_nav = portfolio_returns_to_nav(returns=returns,
                                           init_period=init_period,
                                           init_value=init_value,
                                           freq=freq)
    return grouped_nav


def create_nav_from_returns(returns: Union[pd.Series, pd.DataFrame],
                            init_value: float = 100.0,
                            terminal_value: float = None,
                            first_date: pd.Timestamp = None,
                            nav_limit: Union[float, None] = 10e-8
                            ) -> Union[pd.Series, pd.DataFrame]:

    """
    take returns of several instruments and compute nav with filtering out nansn
    """
    returns = returns.copy()  # just in case create local copy

    if first_date is not None:
        # the nav=100 will start from the first date if given
        # if returns[0] is not zero then first nav will be discounted from 100

        if isinstance(returns, pd.DataFrame):
            first_return = pd.DataFrame(data=0.0, columns=returns.columns, index=[first_date])

        elif isinstance(returns, pd.Series):
            first_return = pd.Series(data=0.0, name=returns.name, index=[first_date])

        else:
            raise TypeError('unsuported returns type')

        returns = pd.concat([first_return, returns])

    if returns.index.is_unique is False:  # check if index is uniques
        returns = returns[~returns.index.duplicated(keep='first')]

    #  remove -+ inf and nans
    returns.replace([np.inf, -np.inf], np.nan, inplace=True)
    returns = returns.fillna(0.0)

    nav = returns.add(1).cumprod()

    if nav_limit is not None:  # fill nan for very small returns
        nav = nav.clip(lower=nav_limit)

    if init_value is not None:
        nav = np.multiply(nav, init_value)

    elif terminal_value is not None:
        ratio = terminal_value / nav.iloc[-1].values
        nav = np.multiply(nav, ratio)

    return nav


def to_zero_first_non_nan_returns(returns: Union[pd.Series, pd.DataFrame],
                                  init_period: Union[int, None] = 1
                                  ) -> Union[pd.Series, pd.DataFrame]:

    """
    replace first nonnan return with zero
    """
    if init_period is not None and not isinstance(init_period, int):
        raise ValueError(f"init_period must be integer")

    if init_period is not None:
        if init_period == 1:
            returns = returns.copy()
            first_before_non_nan_index = dfo.get_first_before_non_nan_index(df=returns)
            first_date = returns.index[0]
            if isinstance(returns, pd.Series):
                if first_before_non_nan_index >= first_date:
                    returns[first_before_non_nan_index] = 0.0
            else:
                for first_before_non_nan_index_, column in zip(first_before_non_nan_index, returns.columns):
                    if first_before_non_nan_index_ >= first_date:
                        returns.loc[first_before_non_nan_index_, column] = 0.0
        else:
            warnings.warn(f"in returns_to_nav init_period={init_period} is not supported")

    return returns


def get_excess_returns_nav(prices: Union[pd.DataFrame, pd.Series],
                           funding_rate: pd.Series,
                           freq: str = 'B'
                           ) -> Union[pd.DataFrame, pd.Series]:

    if not isinstance(funding_rate, pd.Series):
        raise ValueError(f"funding_rate must be series")

    nav_returns = to_returns(prices=prices, freq=freq)

    funding_rate_dt = dfo.multiply_df_by_dt(df=funding_rate, dates=nav_returns.index, lag=1)

    if isinstance(prices, pd.DataFrame):
        n_col = len(prices.columns)
        excess_returns = nav_returns.subtract(npo.np_array_to_df_columns(a=funding_rate_dt.to_numpy(), n_col=n_col),
                                              axis=1)
    else:
        data = nav_returns.to_numpy()-funding_rate_dt.to_numpy()
        excess_returns = pd.Series(data, index=nav_returns.index, name=nav_returns.name)

    terminal_value = dfo.get_last_non_nan_values(prices)
    excess_nav = returns_to_nav(returns=excess_returns,
                                    terminal_value=terminal_value,
                                    init_period=1)
    return excess_nav


class UnitTests(Enum):
    TO_ZERO_NONNAN = 1
    VOL_SAMPLE = 2
    ADJUST_PORTFOLIO_PA_RETURNS = 3
    NET_RETURN = 4


def run_unit_test(unit_test: UnitTests):

    import qis.plots.time_series as pts
    from qis.data.yf_data import load_etf_data
    prices = load_etf_data().dropna()

    if unit_test == UnitTests.TO_ZERO_NONNAN:

        np.random.seed(2)  # freeze seed
        dates = pd.date_range(start='31Dec2020', end='07Jan2021', freq='B')
        n = 3
        returns = pd.DataFrame(data=np.random.normal(0.0, 0.01, (len(dates), n)),
                               index=dates,
                               columns=['x' + str(m + 1) for m in range(n)])

        returns.iloc[:, 0] = np.nan
        returns.iloc[:2, 1] = np.nan
        returns.iloc[:1, 2] = np.nan
        returns.iloc[3, 2] = np.nan

        print(f"returns:\n{returns}")

        returns1 = to_zero_first_non_nan_returns(returns=returns)
        print(f"zero_first_non_nan_returns=\n{returns1}")

        navs = returns_to_nav(returns=returns)
        print(f"navs with init_period = 1:\n{navs}")
        navs = returns_to_nav(returns=returns, init_period=None)
        print(f"navs with init_period = None:\n{navs}")

    elif unit_test == UnitTests.VOL_SAMPLE:

        vols = compute_sampled_vols(prices=prices,
                                    freq_return='B',
                                    freq_vol='M')
        print(vols)

    elif unit_test == UnitTests.ADJUST_PORTFOLIO_PA_RETURNS:

        returns = prices.pct_change()

        portfolio_price = returns_to_nav(returns=returns.sum(1)).rename('portfolio')

        asset_prices_adj = adjust_navs_to_portfolio_pa(portfolio_nav=portfolio_price,
                                                       asset_prices=prices)

        asset_prices_adj.columns = [x + ' adjusted' for x in asset_prices_adj.columns]

        plot_data = pd.concat([prices.divide(prices.iloc[0, :], axis=1),
                               asset_prices_adj.divide(asset_prices_adj.iloc[0, :], axis=1),
                               portfolio_price], axis=1)
        pts.plot_time_series(df=plot_data,
                             var_format='{:.2f}',
                             title='Original vs Adjusted NAVs')
        print(asset_prices_adj)

    elif unit_test == UnitTests.NET_RETURN:

        nav = prices['SPY'].dropna()
        print(nav)
        net_navs = get_net_navs(navs=nav)
        print(net_navs)

    plt.show()


if __name__ == '__main__':

    unit_test = UnitTests.NET_RETURN

    is_run_all_tests = False
    if is_run_all_tests:
        for unit_test in UnitTests:
            run_unit_test(unit_test=unit_test)
    else:
        run_unit_test(unit_test=unit_test)