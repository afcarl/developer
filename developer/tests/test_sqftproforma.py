from __future__ import print_function, division, absolute_import
import os

import pandas as pd
import numpy as np
import pytest

from developer import sqftproforma as sqpf


@pytest.fixture
def simple_dev_inputs():
    return pd.DataFrame(
        {'residential': [40, 40, 40],
         'office': [15, 18, 15],
         'retail': [12, 10, 10],
         'industrial': [12, 12, 12],
         'land_cost': [1000000, 2000000, 3000000],
         'parcel_size': [10000, 20000, 30000],
         'max_far': [2.0, 3.0, 4.0],
         'max_height': [40, 60, 80]},
        index=['a', 'b', 'c'])


@pytest.fixture
def max_dua_dev_inputs():
    sdi = simple_dev_inputs()
    sdi['max_dua'] = [0, 0, 0]
    sdi['ave_unit_size'] = [650, 650, 650]
    return sdi


@pytest.fixture
def simple_dev_inputs_high_cost():
    sdi = simple_dev_inputs()
    sdi.land_cost *= 20
    return sdi


@pytest.fixture
def simple_dev_inputs_low_cost():
    sdi = simple_dev_inputs()
    sdi.land_cost /= 100
    return sdi


def test_sqftproforma_config_defaults():
    sqpf.SqFtProForma.from_defaults()


def test_sqftproforma_to_dict():
    original_config = sqpf.SqFtProForma.get_defaults()
    pf = sqpf.SqFtProForma.from_defaults()
    new_config = pf.to_dict

    assert original_config == new_config


def test_sqftproforma_to_yaml():
    if os.path.exists('test_sqftproforma_config.yaml'):
        os.remove('test_sqftproforma_config.yaml')

    pf = sqpf.SqFtProForma.from_defaults()
    with open('test_sqftproforma_config.yaml', 'w') as yaml_file:
        pf.to_yaml(yaml_file)
        yaml_string = pf.to_yaml()

    pf_from_yaml_file = sqpf.SqFtProForma.from_yaml(
        str_or_buffer='test_sqftproforma_config.yaml')
    assert pf.to_dict == pf_from_yaml_file.to_dict

    pf_from_yaml_string = sqpf.SqFtProForma.from_yaml(
        yaml_str=yaml_string)
    assert pf.to_dict == pf_from_yaml_string.to_dict

    os.remove('test_sqftproforma_config.yaml')


def test_sqftproforma_to_yaml_defaults():
    # Make sure that optional parameters to the SqFtProForma constructor
    # are being read from config

    if os.path.exists('test_sqftproforma_config.yaml'):
        os.remove('test_sqftproforma_config.yaml')

    settings = sqpf.SqFtProForma.get_defaults()
    settings['residential_to_yearly'] = False
    settings['forms_to_test'] = 'residential'
    settings['only_built'] = False
    settings['pass_through'] = ['some_column']
    settings['simple_zoning'] = True
    settings['parcel_filter'] = 'some_expression'

    pf_from_settings = sqpf.SqFtProForma(**settings)
    pf_from_settings.to_yaml('test_sqftproforma_config.yaml')

    pf_from_yaml = sqpf.SqFtProForma.from_yaml(
        str_or_buffer='test_sqftproforma_config.yaml')

    assert pf_from_yaml.to_dict == pf_from_settings.to_dict

    os.remove('test_sqftproforma_config.yaml')


def test_sqftproforma_defaults(simple_dev_inputs):
    pf = sqpf.SqFtProForma.from_defaults()

    for form in pf.forms:
        out = pf.lookup(form, simple_dev_inputs)
        if form == "industrial":
            assert len(out) == 0
        if form == "residential":
            assert len(out) == 3
        if form == "office":
            assert len(out) == 0


def test_sqftproforma_max_dua(simple_dev_inputs_low_cost, max_dua_dev_inputs):
    pf = sqpf.SqFtProForma.from_defaults()

    out = pf.lookup("residential", simple_dev_inputs_low_cost)
    # normal run return 3
    assert len(out) == 3

    out = pf.lookup("residential", max_dua_dev_inputs)
    # max_dua is set to 0
    assert len(out) == 0


def test_sqftproforma_low_cost(simple_dev_inputs_low_cost):
    pf = sqpf.SqFtProForma.from_defaults()

    for form in pf.forms:
        out = pf.lookup(form, simple_dev_inputs_low_cost)
        if form == "industrial":
            assert len(out) == 3
        if form == "residential":
            assert len(out) == 3
        if form == "office":
            assert len(out) == 3


def test_reasonable_feasibility_results():
    pf = sqpf.SqFtProForma.from_defaults()
    df = pd.DataFrame(
        {'residential': [30, 20, 10],
         'office': [15, 15, 15],
         'retail': [12, 12, 12],
         'industrial': [12, 12, 12],
         'land_cost': [1000*100, 1000*100, 1000*100],
         'parcel_size': [1000, 1000, 1000],
         'max_far': [2.0, 2.0, 2.0],
         'max_height': [80, 80, 80]}, index=['a', 'b', 'c'])

    out = pf.lookup("residential", df)
    first = out.iloc[0]
    # far limit is 1.8
    assert first.max_profit_far == 1.8
    # at an far of 1.8, this is the building_sqft
    assert first.building_sqft == 1800
    # confirm cost per sqft is between 100 and 400 per sqft
    assert 100 < first.building_cost/first.building_sqft < 400
    # total cost equals building cost plus land cost
    assert first.total_cost == (first.building_cost
                                + df.iloc[0].land_cost
                                + first.financing_cost)
    # revenue per sqft should be between 200 and 800 per sqft
    assert 200 < first.building_revenue/first.building_sqft < 800
    assert first.residential_sqft == (first.building_sqft
                                      * pf.building_efficiency)
    # because of parcel inefficiency,
    # stories should be greater than far, but not too much more
    assert first.max_profit_far < first.stories < first.max_profit_far * 3.0
    assert first.non_residential_sqft == 0
    assert first.max_profit > 0

    assert len(out) == 1

    # we should be able to reduce parking requirements and build to max far
    defaults = sqpf.SqFtProForma.get_defaults()
    defaults['parking_rates']['residential'] = 0
    pf = sqpf.SqFtProForma(**defaults)
    out = pf.lookup("residential", df)
    second = out.iloc[1]
    assert second.max_profit_far == 2.0


def test_sqftproforma_high_cost(simple_dev_inputs_high_cost):
    pf = sqpf.SqFtProForma.from_defaults()

    for form in pf.forms:
        out = pf.lookup(form, simple_dev_inputs_high_cost)
        if form == "industrial":
            assert len(out) == 0
        if form == "residential":
            assert len(out) == 0
        if form == "office":
            assert len(out) == 0


def test_debug_info():
    pf = sqpf.SqFtProForma.from_defaults()
    for form in pf.forms:
        for parking_config in pf.parking_configs:
            pf.get_debug_info(form, parking_config)


def test_appropriate_range():
    # these are price per sqft costs.  I suppose these could change as
    # time goes on, but for now this is a reasonable range for sqft costs
    pf = sqpf.SqFtProForma.from_defaults()
    for form in pf.forms:
        for park_config in pf.parking_configs:
            s = pf.get_ave_cost_sqft(form, park_config)
            assert len(s[s > 400.0]) == 0
            assert len(s[s < 50.0]) == 0


def test_roughly_monotonic():
    pf = sqpf.SqFtProForma.from_defaults()
    for form in pf.forms:
        for park_config in pf.parking_configs:
            s = pf.get_ave_cost_sqft(form, park_config).values
            for i in range(0, s.size-1):
                left, right = s[i], s[i+1]
                if np.isnan(left) or np.isnan(right):
                    continue
                # actually this doesn't have to perfectly monotonic since
                # construction costs make the function somewhat discontinuous
                assert left < right*1.1


class TestSqFtProFormaDebug(object):
    def teardown_method(self, method):
        if os.path.exists('even_rents.png'):
            os.remove('even_rents.png')

    def test_sqftproforma_debug(self):
        pf = sqpf.SqFtProForma.from_defaults()
        pf._debug_output()
