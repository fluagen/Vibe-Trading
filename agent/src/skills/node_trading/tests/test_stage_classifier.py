"""测试 stage_classifier.py 五阶段判定逻辑。"""

import pytest
from src.skills.node_trading.stage_classifier import classify_stage, is_downtrend


class TestClassifyStage:
    def test_nan_returns_s1(self):
        assert classify_stage(r=float("nan"), cv=0.1, rs=1.0, alignment="bull") == "S1"
        assert classify_stage(r=3.0, cv=float("nan"), rs=1.0, alignment="bull") == "S1"

    def test_s5_extreme(self):
        assert classify_stage(r=10.0, cv=0.5, rs=1.0, alignment="bull") == "S5"

    def test_s4_by_r(self):
        assert classify_stage(r=7.0, cv=0.2, rs=1.0, alignment="bull") == "S4"

    def test_s4_by_rs(self):
        assert classify_stage(r=5.0, cv=0.2, rs=1.2, alignment="bull") == "S4"

    def test_s3_healthy(self):
        assert classify_stage(r=5.0, cv=0.2, rs=1.0, alignment="bull") == "S3"

    def test_s3_bear(self):
        assert classify_stage(r=5.5, cv=0.25, rs=0.9, alignment="bear") == "S3"

    def test_s2_sprout(self):
        assert classify_stage(r=3.0, cv=0.4, rs=1.0, alignment="bull") == "S2"

    def test_s1_sticky_r(self):
        assert classify_stage(r=1.5, cv=0.1, rs=1.0, alignment="bull") == "S1"

    def test_s1_crossed(self):
        assert classify_stage(r=5.0, cv=0.2, rs=0.9, alignment="crossed") == "S1"

    def test_priority_s5_over_s4(self):
        assert classify_stage(r=10.0, cv=0.5, rs=2.0, alignment="bull") == "S5"

    def test_priority_s4_over_s3(self):
        assert classify_stage(r=5.0, cv=0.2, rs=1.5, alignment="bull") == "S4"


class TestIsDowntrend:
    def test_bear_true(self):
        assert is_downtrend("bear") is True

    def test_bull_false(self):
        assert is_downtrend("bull") is False

    def test_crossed_false(self):
        assert is_downtrend("crossed") is False
