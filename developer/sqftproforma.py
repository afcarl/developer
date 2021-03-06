from __future__ import print_function, division, absolute_import
import inspect
import numpy as np
import pandas as pd
import logging
import developer.utils as utils
from developer.utils import columnize

logger = logging.getLogger(__name__)


class SqFtProForma(object):
    """
    Initialize the square foot based pro forma.

    This pro forma has no representation of units - it does not
    differentiate between the rent attained by 1BR, 2BR, or 3BR and change
    the rents accordingly.  This is largely because it is difficult to get
    information on the unit mix in an existing building in order to compute
    its acquisition cost.  Thus rents and costs per sqft are used for new
    and current buildings which assumes there is a constant return on
    increasing and decreasing unit sizes, an extremely useful simplifying
    assumption above the project scale (i.e. city of regional scale)

    Parameters
    ----------
    parcel_sizes : list
        A list of parcel sizes to test.  Interestingly, right now
        the parcel sizes cancel in this style of pro forma computation so
        you can set this to something reasonable for debugging purposes -
        e.g. [10000].  All sizes can be feet or meters as long as they are
        consistently used.
    fars : list
        A list of floor area ratios to use.  FAR is a multiple of
        the parcel size that is the total building bulk that is allowed by
        zoning on the site.  In this case, all of these ratios will be
        tested regardless of zoning and the zoning test will be performed
        later.
    uses : list
        A list of space uses to use within a building.  These are
        mixed into forms.  Generally speaking, you should only have uses
        for which you have an estimate (or observed) values for rents in
        the building.  By default, uses are retail, industrial, office,
        and residential.
    forms : dict
        A dictionary where keys are names for the form and values
        are also dictionaries where keys are uses and values are the
        proportion of that use used in this form.  The values of the
        dictionary should sum to 1.0.  For instance, a form called
        "residential" might have a dict of space allocations equal to
        {"residential": 1.0} while a form called "mixedresidential"
        might have a dictionary of space allocations equal to
        {"retail": .1, "residential" .9] which is 90% residential and
        10% retail.
    parking_rates : dict
        A dict of rates per thousand square feet where keys are the uses
        from the list specified in the attribute above.  The ratios
        are typically in the range 0.5 - 3.0 or similar.  So for
        instance, a key-value pair of "retail": 2.0 would be two parking
        spaces per 1,000 square feet of retail.  This is a per square
        foot pro forma, so the more typically parking ratio of spaces
        per residential unit must be converted to square feet for use in
        this pro forma.
    sqft_per_rate : float
        The number of square feet per unit for use in the
        parking_rates above.  By default this is set to 1,000 but can be
        overridden.
    parking_configs : list
        An expert parameter and is usually unchanged.  By default
        it is set to ['surface', 'deck', 'underground'] and very semantic
        differences in the computation are performed for each of these
        parking configurations.  Generally speaking it will break things
        to change this array, but an item can be removed if that parking
        configuration should not be tested.
    parking_sqft_d : dict
        A dictionary where keys are the three parking
        configurations listed above and values are square foot uses of
        parking spaces in that configuration.  This is to capture the
        fact that surface parking is usually more space intensive
        than deck or underground parking.
    parking_cost_d : dict
        The parking cost for each parking configuration.  Keys are the
        name of the three parking configurations listed above and values
        are dollars PER SQUARE FOOT for parking in that configuration.
        Used to capture the fact that underground and deck are far more
        expensive than surface parking.
    heights_for_costs : list
        A list of "break points" as heights at which construction becomes
        more expensive.  Generally these are the heights at which
        construction materials change from wood, to concrete, to steel.
        Costs are also given as lists by use for each of these break
        points and are considered to be valid up to the break point.  A
        list would look something like [15, 55, 120, np.inf].
    costs : dict
        The keys are uses from the attribute above and the values are a
        list of floating point numbers of same length as the
        height_for_costs attribute.  A key-value pair of
        "residential": [160.0, 175.0, 200.0, 230.0] would say that the
        residential use if $160/sqft up to 15ft in total height for the
        building, $175/sqft up to 55ft, $200/sqft up to 120ft, and
        $230/sqft beyond.  A final value in the height_for_costs
        array of np.inf is typical.
    height_per_story : float
        The per-story height for the building used to turn an
        FAR into an actual height.
    max_retail_height : float
        The maximum height of retail buildings to consider.
    max_industrial_height : float
        The maximum height of industrial buildings to consider.
    construction_months : dict
        Analogous to 'costs', but for building construction time.
        The keys are uses from the attribute above and the values are a
        list of floating-point numbers of same length as the
        construction_sqft_for_months attribute. A key-value pair of
        "residential": [12.0, 14.0, 18.0, 24.0] along with the default values
        for construction_sqft_for_months below would say that buildings with
        10,000 sq. ft. or less take 12 months, those between 10,000 and 20,000
        sq. ft. take 14 months, etc.
    construction_sqft_for_months:
        Analogous to heights_for_costs, but for building construction time.
        A list of "break points" as building square footage at which
        construction takes a different length of time. Default values are
        [10000, 20000, 50000, np.inf].
    loan_to_cost_ratio : float
        The proportion of construction loans to the total construction cost.
    drawdown_factor : float
        The factor by which financing cost is reduced by applying interest
        only to funds withdrawn in phases.
    interest_rate : float
        The interest rate for construction loans
    loan_fees : float
        The percentage of loan size that is added to costs as other fees
    profit_factor : float
        The ratio of profit a developer expects to make above the break
        even rent.  Should be greater than 1.0, e.g. a 10% profit would be
        a profit factor of 1.1.
    building_efficiency : float
        The efficiency of the building.  This turns total FAR into the
        amount of space which gets a square foot rent.  The entire building
        gets the cost of course.
    parcel_coverage : float
        The ratio of the building footprint to the parcel size.  Also used
        to turn an FAR into a height to cost properly.
    cap_rate : float
        The rate an investor is willing to pay for a cash flow per year.
        This means $1/year is equivalent to 1/cap_rate present dollars.
        This is a macroeconomic input that is widely available on the
        internet.
    residential_to_yearly : boolean (optional)
        Whether to use the cap rate to convert the residential price from total
        sales price per sqft to rent per sqft
    forms_to_test : list of strings (optional)
        Pass the list of the names of forms to test for feasibility - if set to
        None will use all the forms available in config
    only_built : boolean (optional)
        Only return those buildings that are profitable
    pass_through : list of strings (optional)
        Will be passed to the feasibility lookup function - is used to pass
        variables from the parcel dataframe to the output dataframe, usually
        for debugging
    simple_zoning: boolean (optional)
        This can be set to use only max_dua for residential and max_far for
        non-residential.  This can be handy if you want to deal with zoning
        outside of the developer model.
    parcel_filter : string (optional)
        A filter to apply to the parcels data frame to remove parcels from
        consideration - is typically used to remove parcels with buildings
        older than a certain date for historical preservation, but is
        generally useful

    """

    def __init__(self, parcel_sizes, fars, uses, residential_uses, forms,
                 profit_factor, building_efficiency, parcel_coverage,
                 cap_rate, parking_rates, sqft_per_rate, parking_configs,
                 costs, heights_for_costs, parking_sqft_d, parking_cost_d,
                 height_per_story, max_retail_height, max_industrial_height,
                 construction_months, construction_sqft_for_months,
                 loan_to_cost_ratio, drawdown_factor, interest_rate, loan_fees,
                 residential_to_yearly=True, forms_to_test=None,
                 only_built=True, pass_through=None, simple_zoning=False,
                 parcel_filter=None
                 ):

        self.parcel_sizes = parcel_sizes
        self.fars = fars
        self.uses = uses
        self.residential_uses = residential_uses
        self.forms = forms
        self.profit_factor = profit_factor
        self.building_efficiency = building_efficiency
        self.parcel_coverage = parcel_coverage
        self.cap_rate = cap_rate
        self.parking_rates = parking_rates
        self.sqft_per_rate = sqft_per_rate
        self.parking_configs = parking_configs
        self.costs = costs
        self.heights_for_costs = heights_for_costs
        self.parking_sqft_d = parking_sqft_d
        self.parking_cost_d = parking_cost_d
        self.height_per_story = height_per_story
        self.max_retail_height = max_retail_height
        self.max_industrial_height = max_industrial_height
        self.construction_months = construction_months
        self.construction_sqft_for_months = construction_sqft_for_months
        self.loan_to_cost_ratio = loan_to_cost_ratio
        self.drawdown_factor = drawdown_factor
        self.interest_rate = interest_rate
        self.loan_fees = loan_fees

        self.residential_to_yearly = residential_to_yearly
        self.forms_to_test = forms_to_test or sorted(self.forms.keys())
        self.only_built = only_built
        self.pass_through = [] if pass_through is None else pass_through
        self.simple_zoning = simple_zoning
        self.parcel_filter = parcel_filter

        self.check_is_reasonable()
        self._convert_types()

        reference = SqFtProFormaReference(**self.__dict__)
        self.reference_dict = reference.reference_dict

    def check_is_reasonable(self):
        fars = pd.Series(self.fars)
        assert len(fars[fars > 20]) == 0
        assert len(fars[fars <= 0]) == 0
        for k, v in self.forms.items():
            assert isinstance(v, dict)
            for k2, v2 in self.forms[k].items():
                assert isinstance(k2, str)
                assert isinstance(v2, float)
            for k2, v2 in self.forms[k].items():
                assert isinstance(k2, str)
                assert isinstance(v2, float)
        for k, v in self.parking_rates.items():
            assert isinstance(k, str)
            assert k in self.uses
            assert 0 <= v < 5
        for k, v in self.parking_sqft_d.items():
            assert isinstance(k, str)
            assert k in self.parking_configs
            assert 50 <= v <= 1000
        for k, v in self.parking_sqft_d.items():
            assert isinstance(k, str)
            assert k in self.parking_cost_d
            assert 10 <= v <= 300
        for v in self.heights_for_costs:
            assert isinstance(v, int) or isinstance(v, float)
            if np.isinf(v):
                continue
            assert 0 <= v <= 1000
        for k, v in self.costs.items():
            assert isinstance(k, str)
            assert k in self.uses
            for i in v:
                assert 10 < i < 1000

    def _convert_types(self):
        """
        convert lists and dictionaries that are useful for users to
        np vectors that are usable by machines

        """
        self.fars = np.array(self.fars)
        self.parking_rates = np.array(
            [self.parking_rates[use] for use in self.uses])
        self.res_ratios = {}
        assert len(self.uses) == len(self.residential_uses)
        for k, v in self.forms.items():
            self.forms[k] = np.array(
                [self.forms[k].get(use, 0.0) for use in self.uses])
            # normalize if not already
            self.forms[k] /= self.forms[k].sum()
            self.res_ratios[k] = pd.Series(self.forms[k])[
                self.residential_uses].sum()
        self.costs = np.transpose(
            np.array([self.costs[use] for use in self.uses]))
        self.construction_months = np.transpose(
            np.array([self.construction_months[use] for use in self.uses])
        )

    @classmethod
    def from_yaml(cls, yaml_str=None, str_or_buffer=None):
        """
        Create a SqftProForma instance from a saved YAML configuration.
        Arguments are mutally exclusive.

        Parameters
        ----------
        yaml_str : str, optional
            A YAML string from which to load model.
        str_or_buffer : str or file like, optional
            File name or buffer from which to load YAML.

        Returns
        -------
        SqFtProForma

        """
        cfg = utils.yaml_to_dict(yaml_str, str_or_buffer)

        model = cls(
            cfg['parcel_sizes'], cfg['fars'], cfg['uses'],
            cfg['residential_uses'], cfg['forms'], cfg['profit_factor'],
            cfg['building_efficiency'], cfg['parcel_coverage'],
            cfg['cap_rate'], cfg['parking_rates'], cfg['sqft_per_rate'],
            cfg['parking_configs'], cfg['costs'], cfg['heights_for_costs'],
            cfg['parking_sqft_d'], cfg['parking_cost_d'],
            cfg['height_per_story'], cfg['max_retail_height'],
            cfg['max_industrial_height'],
            cfg['construction_months'],
            cfg['construction_sqft_for_months'],
            cfg['loan_to_cost_ratio'],
            cfg['drawdown_factor'],
            cfg['interest_rate'],
            cfg['loan_fees'],
            cfg.get('residential_to_yearly', True),
            cfg.get('forms_to_test', None),
            cfg.get('only_built', True),
            cfg.get('pass_through', None),
            cfg.get('simple_zoning', False),
            cfg.get('parcel_filter', None)
        )

        logger.debug('loaded SqftProForma model from YAML')
        return model

    @staticmethod
    def get_defaults():
        return {'building_efficiency': 0.7,
                'cap_rate': 0.05,
                'costs': {'industrial': [140.0, 175.0, 200.0, 230.0],
                          'office': [160.0, 175.0, 200.0, 230.0],
                          'residential': [170.0, 190.0, 210.0, 240.0],
                          'retail': [160.0, 175.0, 200.0, 230.0]},
                'fars': [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 1.8,
                         2.0, 2.25, 2.5, 2.75, 3.0, 3.25,
                         3.5, 3.75, 4.0, 4.5, 5.0, 5.5, 6.0,
                         6.5, 7.0, 9.0, 11.0],
                'forms': {'industrial': {'industrial': 1.0},
                          'mixedoffice': {'office': 0.7, 'residential': 0.3},
                          'mixedresidential': {'residential': 0.9,
                                               'retail': 0.1},
                          'office': {'office': 1.0},
                          'residential': {'residential': 1.0},
                          'retail': {'retail': 1.0}},
                'height_per_story': 12.0,
                'heights_for_costs': [15, 55, 120, np.inf],
                'max_industrial_height': 2.0,
                'max_retail_height': 2.0,
                'parcel_coverage': 0.8,
                'parcel_sizes': [10000.0],
                'parking_configs': ['surface', 'deck', 'underground'],
                'parking_cost_d': {'deck': 90, 'surface': 30,
                                   'underground': 110},
                'parking_rates': {'industrial': 0.6,
                                  'office': 1.0,
                                  'residential': 1.0,
                                  'retail': 2.0},
                'parking_sqft_d': {'deck': 250.0, 'surface': 300.0,
                                   'underground': 250.0},
                'profit_factor': 1.1,
                'residential_uses': [False, False, False, True],
                'sqft_per_rate': 1000.0,
                'uses': ['retail', 'industrial', 'office', 'residential'],
                'residential_to_yearly': True,
                'parcel_filter': None,
                'only_built': True,
                'forms_to_test': ['industrial', 'mixedoffice',
                                  'mixedresidential', 'office',
                                  'residential', 'retail'],
                'pass_through': [],
                'simple_zoning': False,
                'construction_months': {
                    'industrial': [12.0, 14.0, 18.0, 24.0],
                    'office': [12.0, 14.0, 18.0, 24.0],
                    'residential': [12.0, 14.0, 18.0, 24.0],
                    'retail': [12.0, 14.0, 18.0, 24.0]},
                'construction_sqft_for_months': [10000, 20000, 50000, np.inf],
                'loan_to_cost_ratio': .7,
                'drawdown_factor': .6,
                'interest_rate': .05,
                'loan_fees': .02
                }

    @classmethod
    def from_defaults(cls):
        """
        Create a SqftProForma instance from default values.

        Returns
        -------
        SqFtProForma

        """

        defaults = SqFtProForma.get_defaults()
        model = cls(**defaults)
        logger.debug('loaded SqftProForma model from default values')
        return model

    @property
    def to_dict(self):
        """
        Return a dict representation of a SqftProForma instance.

        """

        unconverted = ['parcel_sizes', 'uses', 'residential_uses',
                       'profit_factor', 'building_efficiency',
                       'parcel_coverage', 'cap_rate', 'sqft_per_rate',
                       'parking_configs', 'heights_for_costs',
                       'parking_sqft_d', 'parking_cost_d', 'height_per_story',
                       'max_retail_height', 'max_industrial_height',
                       'residential_to_yearly', 'parcel_filter', 'only_built',
                       'forms_to_test', 'pass_through', 'simple_zoning',
                       'construction_sqft_for_months', 'loan_to_cost_ratio',
                       'drawdown_factor', 'interest_rate', 'loan_fees']

        results = {}
        for attribute in unconverted:
            results[attribute] = self.__dict__[attribute]

        # Un-convert converted attributes from _convert_types() method

        results['fars'] = self.fars.tolist()

        parking_rates = {}
        for index, use in enumerate(self.uses):
            rate_for_use = self.parking_rates[index]
            parking_rates[use] = float(rate_for_use)
        results['parking_rates'] = parking_rates

        forms = {}
        for form_name, form_array in self.forms.items():
            form_dict = {}
            for index, use in enumerate(self.uses):
                use_percentage = form_array[index]
                if use_percentage != 0:
                    form_dict[use] = float(form_array[index])
            forms[form_name] = form_dict
        results['forms'] = forms

        costs = {}
        costs_transposed = self.costs.transpose()
        for index, use in enumerate(self.uses):
            values = costs_transposed[index]
            costs[use] = values.tolist()
        results['costs'] = costs

        time = {}
        time_transposed = self.construction_months.transpose()
        for index, use in enumerate(self.uses):
            values = time_transposed[index]
            time[use] = values.tolist()
        results['construction_months'] = time

        return results

    def to_yaml(self, str_or_buffer=None):
        """
        Save a model representation to YAML.

        Parameters
        ----------
        str_or_buffer : str or file like, optional
            By default a YAML string is returned. If a string is
            given here the YAML will be written to that file.
            If an object with a ``.write`` method is given the
            YAML will be written to that object.

        Returns
        -------
        j : str
            YAML is string if `str_or_buffer` is not given.

        """
        logger.debug('serializing SqftProForma model to YAML')
        return utils.convert_to_yaml(self.to_dict, str_or_buffer)

    def lookup(self, form, df, modify_df=None, modify_revenues=None,
               modify_costs=None, modify_profits=None, **kwargs):
        """
        This function does the developer model lookups for all the actual input
        data.

        Parameters
        ----------
        form : string
            One of the forms specified in the configuration file
        df : DataFrame
            Pass in a single data frame which is indexed by parcel_id and has
            the following columns
        modify_df : function
            Function to modify lookup DataFrame before profit calculations.
            Must have (self, form, df) as parameters.
        modify_revenues : function
            Function to modify revenue ndarray during profit calculations.
            Must have (self, form, df, revenues) as parameters.
        modify_costs : function
            Function to modify cost ndarray during profit calculations.
            Must have (self, form, df, costs) as parameters.
        modify_profits : function
            Function to modify profit ndarray during profit calculations.
            Must have (self, form, df, profits) as parameters.

        Input Dataframe Columns
        rent : dataframe
            A set of columns, one for each of the uses passed in the
            configuration. Values are yearly rents for that use. Typical column
            names would be "residential", "retail", "industrial" and "office"
        land_cost : series
            A series representing the CURRENT yearly rent for each parcel.
            Used to compute acquisition costs for the parcel.
        parcel_size : series
            A series representing the parcel size for each parcel.
        max_far : series
            A series representing the maximum far allowed by zoning.  Buildings
            will not be built above these fars.
        max_height : series
            A series representing the maximum height allowed by zoning.
            Buildings will not be built above these heights.  Will pick between
            the min of the far and height, will ignore on of them if one is
            nan, but will not build if both are nan.
        max_dua : series, optional
            A series representing the maximum dwelling units per acre allowed
            by zoning.  If max_dua is passed, the average unit size should be
            passed below to translate from dua to floor space.
        ave_unit_size : series, optional
            This is required if max_dua is passed above, otherwise it is
            optional. This is the same as the parameter to Developer.pick()
            (it should be the same series).

        Returns
        -------
        index : Series, int
            parcel identifiers
        building_sqft : Series, float
            The number of square feet for the building to build.  Keep in mind
            this includes parking and common space.  Will need a helpful
            function to convert from gross square feet to actual usable square
            feet in residential units.
        building_cost : Series, float
            The cost of constructing the building as given by the
            ave_cost_per_sqft from the cost model (for this FAR) and the number
            of square feet.
        total_cost : Series, float
            The cost of constructing the building plus the cost of acquisition
            of the current parcel/building.
        building_revenue : Series, float
            The NPV of the revenue for the building to be built, which is the
            number of square feet times the yearly rent divided by the cap
            rate (with a few adjustment factors including building efficiency).
        max_profit_far : Series, float
            The FAR of the maximum profit building (constrained by the max_far
            and max_height from the input dataframe).
        max_profit :
            The profit for the maximum profit building (constrained by the
            max_far and max_height from the input dataframe).
        """

        if self.simple_zoning:
            df = self._simple_zoning(form, df)

        lookup = pd.concat(
            self._lookup_parking_cfg(form, parking_config, df, modify_df,
                                     modify_revenues, modify_costs,
                                     modify_profits)
            for parking_config in self.parking_configs)

        if len(lookup) == 0:
            return pd.DataFrame()

        result = self._max_profit_parking(lookup)

        if self.residential_to_yearly and "residential" in self.pass_through:
            result["residential"] /= self.cap_rate

        return result

    @staticmethod
    def _simple_zoning(form, df):
        """
        Replaces max_height and either max_far or max_dua with NaNs

        Parameters
        ----------
        form : str
            Name of form passed to lookup method
        df : DataFrame
            DataFrame passed to lookup method

        Returns
        -------
        df : DataFrame
        """

        if form == "residential":
            # these are new computed in the effective max_dua method
            df["max_far"] = pd.Series()
            df["max_height"] = pd.Series()
        else:
            # these are new computed in the effective max_far method
            df["max_dua"] = pd.Series()
            df["max_height"] = pd.Series()

        return df

    @staticmethod
    def _max_profit_parking(df):
        """
        Return parcels DataFrame with parking configuration that maximizes
        profit

        Parameters
        ----------
        df: DataFrame
            DataFrame passed to lookup method

        Returns
        -------
        result : DataFrame
        """

        max_profit_ind = df.pivot(
            columns="parking_config",
            values="max_profit").idxmax(axis=1).to_frame("parking_config")

        df.set_index(["parking_config"], append=True, inplace=True)
        max_profit_ind.set_index(["parking_config"], append=True,
                                 inplace=True)

        # get the max_profit idx
        result = df.loc[max_profit_ind.index].reset_index(1)

        return result

    def _lookup_parking_cfg(self, form, parking_config, df,
                            modify_df, modify_revenues, modify_costs,
                            modify_profits):
        """
        This is the core square foot pro forma calculation. For each form and
        parking configuration, generate DataFrame with profitability
        information

        Parameters
        ----------
        form : str
            Name of form
        parking_config : str
            Name of parking configuration
        df : DataFrame
            DataFrame of developable sites/parcels passed to lookup() method
        modify_df : func
            Function to modify lookup DataFrame before profit calculations.
            Must have (self, form, df) as parameters.
        modify_revenues : func
            Function to modify revenue ndarray during profit calculations.
            Must have (self, form, df, revenues) as parameters.
        modify_costs : func
            Function to modify cost ndarray during profit calculations.
            Must have (self, form, df, costs) as parameters.
        modify_profits : func
            Function to modify profit ndarray during profit calculations.
            Must have (self, form, df, profits) as parameters.

        Returns
        -------
        outdf : DataFrame
        """
        # don't really mean to edit the df that's passed in
        df = df.copy()

        # Reference table for this form and parking configuration
        dev_info = self.reference_dict[(form, parking_config)]

        # Helper values
        cost_sqft_col = columnize(dev_info.ave_cost_sqft.values)
        cost_sqft_index_col = columnize(dev_info.index.values)
        parking_sqft_ratio = columnize(dev_info.parking_sqft_ratio.values)
        heights = columnize(dev_info.height.values)
        months = columnize(dev_info.construction_months.values)
        resratio = self.res_ratios[form]
        nonresratio = 1.0 - resratio
        df['weighted_rent'] = np.dot(df[self.uses], self.forms[form])

        # Allow for user modification of DataFrame here
        df = modify_df(self, form, df) if modify_df else df

        # ZONING FILTERS
        # Minimize between max_fars and max_heights
        df['max_far_from_heights'] = (df.max_height
                                      / self.height_per_story
                                      * self.parcel_coverage)

        df['min_max_fars'] = self._min_max_fars(df, resratio)

        if self.only_built:
            df = df.query('min_max_fars > 0 and parcel_size > 0')

        # turn fars and heights into nans which are not allowed by zoning
        # (so we can fillna with one of the other zoning constraints)
        fars = np.repeat(cost_sqft_index_col, len(df.index), axis=1)
        mask = ~np.isnan(fars)  # mask out existing nans for safer comparison
        mask *= np.nan_to_num(fars) > df.min_max_fars.values + .01
        fars[mask] = np.nan

        heights = np.repeat(heights, len(df.index), axis=1)
        mask = ~np.isnan(heights)
        mask *= np.nan_to_num(heights) > df.max_height.values + .01
        fars[mask] = np.nan

        # PROFIT CALCULATION
        # parcel sizes * possible fars
        building_bulks = fars * df.parcel_size.values

        # cost to build the new building
        building_costs = building_bulks * cost_sqft_col

        # add cost to buy the current building
        total_construction_costs = building_costs + df.land_cost.values

        # Financing costs
        loan_amount = total_construction_costs * self.loan_to_cost_ratio
        months = np.repeat(months, len(df.index), axis=1)
        interest = (loan_amount
                    * self.drawdown_factor
                    * (self.interest_rate / 12 * months))
        points = loan_amount * self.loan_fees
        total_financing_costs = interest + points
        total_development_costs = (total_construction_costs
                                   + total_financing_costs)

        # rent to make for the new building
        building_revenue = (building_bulks
                            * (1 - parking_sqft_ratio)
                            * self.building_efficiency
                            * df.weighted_rent.values
                            / self.cap_rate)

        # profit for each form, including user modification of
        # revenues, costs, and/or profits

        building_revenue = (modify_revenues(self, form, df, building_revenue)
                            if modify_revenues else building_revenue)

        total_development_costs = (
            modify_costs(self, form, df, total_development_costs)
            if modify_costs else total_development_costs)

        profit = building_revenue - total_development_costs

        profit = (modify_profits(self, form, df, profit)
                  if modify_profits else profit)

        profit = profit.astype('float')
        profit[np.isnan(profit)] = -np.inf
        maxprofitind = np.argmax(profit, axis=0)

        def twod_get(indexes, arr):
            return arr[indexes, np.arange(indexes.size)].astype('float')

        outdf = pd.DataFrame({
            'building_sqft': twod_get(maxprofitind, building_bulks),
            'building_cost': twod_get(maxprofitind, building_costs),
            'parking_ratio': parking_sqft_ratio[maxprofitind].flatten(),
            'stories': twod_get(maxprofitind,
                                heights) / self.height_per_story,
            'total_cost': twod_get(maxprofitind, total_development_costs),
            'building_revenue': twod_get(maxprofitind, building_revenue),
            'max_profit_far': twod_get(maxprofitind, fars),
            'max_profit': twod_get(maxprofitind, profit),
            'parking_config': parking_config,
            'construction_time': twod_get(maxprofitind, months),
            'financing_cost': twod_get(maxprofitind, total_financing_costs)
        }, index=df.index)

        if self.pass_through:
            outdf[self.pass_through] = df[self.pass_through]

        outdf["residential_sqft"] = (outdf.building_sqft *
                                     self.building_efficiency *
                                     resratio)
        outdf["non_residential_sqft"] = (outdf.building_sqft *
                                         self.building_efficiency *
                                         nonresratio)

        if self.only_built:
            outdf = outdf.query('max_profit > 0').copy()
        else:
            outdf = outdf.loc[outdf.max_profit != -np.inf].copy()

        return outdf

    def _min_max_fars(self, df, resratio):
        """
        In case max_dua is passed in the DataFrame,
        now also minimize with max_dua from zoning - since this pro forma is
        really geared toward per sqft metrics, this is a bit tricky.  dua
        is converted to floorspace and everything just works (floor space
        will get covered back to units in developer.pick() but we need to
        test the profitability of the floorspace allowed by max_dua here.

        Parameters
        ----------
        df : DataFrame
            DataFrame of developable sites/parcels passed to lookup() method
        resratio : numeric
            Residential ratio for this form

        Returns
        -------
        Series
        """

        if 'max_dua' in df.columns and resratio > 0:
            # if max_dua is in the data frame, ave_unit_size must also be there
            assert 'ave_unit_size' in df.columns

            df['max_far_from_dua'] = (
                # this is the max_dua times the parcel size in acres, which
                # gives the number of units that are allowable on the parcel
                df.max_dua * (df.parcel_size / 43560) *

                # times by the average unit size which gives the square footage
                # of those units
                df.ave_unit_size /

                # divided by the building efficiency which is a
                # factor that indicates that the actual units are not the whole
                # FAR of the building
                self.building_efficiency /

                # divided by the resratio which is a  factor that indicates
                # that the actual units are not the only use of the building
                resratio /

                # divided by the parcel size again in order to get FAR.
                # I recognize that parcel_size actually
                # cancels here as it should, but the calc was hard to get right
                # and it's just so much more transparent to have it in there
                # twice
                df.parcel_size)
            return df[['max_far_from_heights',
                       'max_far', 'max_far_from_dua']].min(axis=1)
        else:
            return df[
                ['max_far_from_heights', 'max_far']].min(axis=1)

    def get_debug_info(self, form, parking_config):
        """
        Get the debug info after running the pro forma for a given form and
        parking configuration

        Parameters
        ----------
        form : string
            The form to get debug info for
        parking_config : string
            The parking configuration to get debug info for

        Returns
        -------
        debug_info : dataframe
            A dataframe where the index is the far with many columns
            representing intermediate steps in the pro forma computation.
            Additional documentation will be added at a later date, although
            many of the columns should be fairly self-expanatory.

        """
        return self.reference_dict[(form, parking_config)]

    def get_ave_cost_sqft(self, form, parking_config):
        """
        Get the average cost per sqft for the pro forma for a given form

        Parameters
        ----------
        form : string
            Get a series representing the average cost per sqft for each form
            in the config
        parking_config : string
            The parking configuration to get debug info for

        Returns
        -------
        cost : series
            A series where the index is the far and the values are the average
            cost per sqft at which the building is "break even" given the
            configuration parameters that were passed at run time.
        """
        return self.reference_dict[(form, parking_config)].ave_cost_sqft

    def _debug_output(self):
        """
        this code creates the debugging plots to understand
        the behavior of the hypothetical building model

        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        df_d = self.reference_dict
        keys = list(df_d.keys())
        keys.sort()
        for key in keys:
            logger.debug("\n" + str(key) + "\n")
            logger.debug(df_d[key])
        for form in self.forms:
            logger.debug("\n" + str(key) + "\n")
            logger.debug(self.get_ave_cost_sqft(form, "surface"))

        keys = list(self.forms.keys())
        keys.sort()
        cnt = 1
        share = None
        fig = plt.figure(figsize=(12, 3 * len(keys)))
        fig.suptitle('Profitable rents by use', fontsize=40)
        for name in keys:
            sumdf = None
            for parking_config in self.parking_configs:
                df = df_d[(name, parking_config)]
                if sumdf is None:
                    sumdf = pd.DataFrame(df['far'])
                sumdf[parking_config] = df['ave_cost_sqft']
            far = sumdf['far']
            del sumdf['far']

            if share is None:
                share = plt.subplot(len(keys) / 2, 2, cnt)
            else:
                plt.subplot(len(keys) / 2, 2, cnt, sharex=share,
                            sharey=share)

            handles = plt.plot(far, sumdf)
            plt.ylabel('even_rent')
            plt.xlabel('FAR')
            plt.title('Rents for use type %s' % name)
            plt.legend(
                handles, self.parking_configs, loc='lower right',
                title='Parking type')
            cnt += 1
        plt.savefig('even_rents.png', bbox_inches=0)


class SqFtProFormaReference(object):
    """
    Generate reference table for square foot pro forma analysis. Table is saved
    as the `reference_dict` attribute.
    """

    def __init__(self, parcel_sizes, fars, forms,
                 profit_factor, parcel_coverage, parking_rates, sqft_per_rate,
                 parking_configs, costs, heights_for_costs, parking_sqft_d,
                 parking_cost_d, height_per_story, max_retail_height,
                 max_industrial_height, construction_sqft_for_months,
                 construction_months, **kwargs):

        self.fars = fars
        self.parcel_sizes = parcel_sizes
        self.forms = forms
        self.profit_factor = profit_factor
        self.parcel_coverage = parcel_coverage
        self.parking_rates = parking_rates
        self.sqft_per_rate = sqft_per_rate
        self.parking_configs = parking_configs
        self.costs = costs
        self.heights_for_costs = heights_for_costs
        self.parking_sqft_d = parking_sqft_d
        self.parking_cost_d = parking_cost_d
        self.height_per_story = height_per_story
        self.max_retail_height = max_retail_height
        self.max_industrial_height = max_industrial_height
        self.construction_sqft_for_months = construction_sqft_for_months
        self.construction_months = construction_months

        self.tiled_parcel_sizes = columnize(
            np.repeat(self.parcel_sizes, self.fars.size))

        self.reference_dict = self._generate_reference()

    def _generate_reference(self):
        """
        Run the developer model on all possible inputs specified in the
        configuration object - not generally called by the user.  This part
        computes the final cost per sqft of the building to construct and
        then turns it into the yearly rent necessary to make break even on
        that cost.

        """

        # get all the building forms we can use
        keys = list(self.forms.keys())
        keys.sort()
        df_d = {}
        for name in keys:
            # get the use distribution for each
            uses_distrib = self.forms[name]

            for parking_config in self.parking_configs:

                df = self._reference_dataframe(name, uses_distrib,
                                               parking_config)
                df_d[(name, parking_config)] = df

        return df_d

    def _reference_dataframe(self, name, uses_distrib, parking_config):
        """
        This generates a reference DataFrame for each form and parking
        configuration, which provides development information for various
        floor-to-area ratios.

        Parameters
        ----------
        name : str
            Name of form
        uses_distrib : ndarray
            The distribution of uses in this form
        parking_config : str
            Name of parking configuration

        Returns
        -------
        df : DataFrame
        """

        df = pd.DataFrame(index=self.fars)

        # Array of square footage values for each FAR
        building_bulk = self._building_bulk(uses_distrib, parking_config)

        # Array of parking stalls required for each FAR
        parking_stalls = (building_bulk
                          * np.sum(uses_distrib * self.parking_rates)
                          / self.sqft_per_rate)

        # Array of stories built at each FAR
        stories = self._stories(parking_config, building_bulk, parking_stalls)

        # Square feet of parking required for this configuration (constant)
        park_sqft = self._park_sqft(parking_config, parking_stalls)

        # Array of total parking cost required for each FAR
        park_cost = (self.parking_cost_d[parking_config]
                     * parking_stalls
                     * self.parking_sqft_d[parking_config])

        # Array of building cost per square foot for each FAR
        building_cost_per_sqft = self._building_cost(uses_distrib, stories)

        total_built_sqft = building_bulk + park_sqft

        # Array of construction time for each FAR
        construction_months = self._construction_time(uses_distrib,
                                                      total_built_sqft)

        df['far'] = self.fars
        df['pclsz'] = self.tiled_parcel_sizes
        df['building_sqft'] = building_bulk
        df['spaces'] = parking_stalls
        df['park_sqft'] = park_sqft
        df['total_built_sqft'] = total_built_sqft
        df['parking_sqft_ratio'] = df.park_sqft / df.total_built_sqft
        df['stories'] = np.ceil(stories)
        df['height'] = df.stories * self.height_per_story
        df['build_cost_sqft'] = building_cost_per_sqft
        df['build_cost'] = df.build_cost_sqft * df.building_sqft
        df['park_cost'] = park_cost
        df['cost'] = df.build_cost + df.park_cost
        df['ave_cost_sqft'] = ((df.cost / df.total_built_sqft)
                               * self.profit_factor)
        df['construction_months'] = construction_months

        if name == 'retail':
            retail_fars_over_max = self.fars > self.max_retail_height
            df.loc[retail_fars_over_max, 'ave_cost_sqft'] = np.nan
        if name == 'industrial':
            industrial_fars_over_max = self.fars > self.max_industrial_height
            df.loc[industrial_fars_over_max, 'ave_cost_sqft'] = np.nan

        return df

    def _building_cost(self, use_mix, stories):
        """
        Generate building cost for a set of buildings

        Parameters
        ----------
        use_mix : array
            The mix of uses for this form
        stories : series
            A Pandas Series of stories

        Returns
        -------
        array
            The cost per sqft for this unit mix and height.

        """

        # stories to heights
        heights = stories * self.height_per_story
        # cost index for this height
        costs = np.searchsorted(self.heights_for_costs, heights)
        # this will get set to nan later
        costs[np.isnan(heights)] = 0
        # compute cost with matrix multiply
        costs = np.dot(np.squeeze(self.costs[costs.astype('int32')]),
                       use_mix)
        # some heights aren't allowed - cost should be nan
        costs[np.isnan(stories).flatten()] = np.nan
        return costs.flatten()

    def _building_bulk(self, uses_distrib, parking_config):
        """
        Multiplies parcel sizes by FARs, with adjustment for deck parking.

        Parameters
        ----------
        uses_distrib : ndarray
            The distribution of uses in this form
        parking_config : str
            Name of current parking configuration

        Returns
        -------
        building_bulk : ndarray
        """

        building_bulk = (columnize(self.parcel_sizes) *
                         columnize(self.fars))
        building_bulk = columnize(building_bulk)

        # need to converge in on exactly how much far is available for
        # deck pkg
        if parking_config == 'deck':
            building_bulk /= (
                1.0 + np.sum(uses_distrib * self.parking_rates) *
                self.parking_sqft_d[parking_config] /
                self.sqft_per_rate)

        return building_bulk

    def _park_sqft(self, parking_config, parking_stalls):
        """
        Generate building square footage required for a parking configuration

        Parameters
        ----------
        parking_config : str
            Name of parking configuration
        parking_stalls : numeric
            Number of parking stalls required

        Returns
        -------
        park_sqft : numeric
        """

        if parking_config in ['underground', 'deck']:
            return parking_stalls * self.parking_sqft_d[parking_config]
        if parking_config == 'surface':
            return 0

    def _stories(self, parking_config, building_bulk, parking_stalls):
        """
        Calculates number of stories built at various FARs, given
        building bulk, number of parking stalls, and parking configuration

        Parameters
        ----------
        parking_config : str
            Name of parking configuration
        building_bulk : ndarray
            Array of total square footage values for each FAR
        parking_stalls : ndarray
            Number of parking stalls required for each FAR

        Returns
        -------
        stories : ndarray

        """

        if parking_config == 'underground':
            stories = building_bulk / self.tiled_parcel_sizes
        if parking_config == 'deck':
            stories = ((building_bulk
                        + parking_stalls
                        * self.parking_sqft_d[parking_config])
                       / self.tiled_parcel_sizes)
        if parking_config == 'surface':
            stories = (building_bulk
                       / (self.tiled_parcel_sizes
                          - parking_stalls
                          * self.parking_sqft_d[parking_config]))
            # not all fars support surface parking
            mask = ~np.isnan(stories)  # mask out existing nans
            mask[mask] *= stories[mask] < 0.0
            stories[mask] = np.nan
            # I think we can assume that stories over 3
            # do not work with surface parking
            mask = ~np.isnan(stories)
            mask[mask] *= stories[mask] > 5.0
            stories[mask] = np.nan

        stories /= self.parcel_coverage

        return stories

    def _construction_time(self, use_mix, building_bulks):
        """
        Calculate construction time in months for each development site.

        Parameters
        ----------
        use_mix : array
            The mix of uses for this form
        building_bulks : array
            Array of square footage for each potential building

        Returns
        -------
        construction_times : array
        """

        # Look at square footage and return matching index in list of
        # construction times
        month_indices = np.searchsorted(self.construction_sqft_for_months,
                                        building_bulks)
        # Get the construction time for each dev site, for all uses
        months_array_all_uses = self.construction_months[month_indices]
        # Dot product to get appropriate time for uses being evaluated
        construction_times = np.dot(months_array_all_uses, use_mix)
        return construction_times
