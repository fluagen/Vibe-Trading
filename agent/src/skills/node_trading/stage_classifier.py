"""五阶段判定模块（S1-S5）。按 PRD 优先级自上而下判定。"""

from __future__ import annotations
import pandas as pd


def classify_stage(
    r: float, cv: float, rs: float, alignment: str,
    *, r_s5: float = 9.0, cv_s5: float = 0.4, r_s4: float = 6.0,
    rs_s4: float = 1.1, r_s3_lower: float = 4.0, r_s3_upper: float = 6.0,
    cv_s3: float = 0.3, r_s2_lower: float = 2.0, r_s2_upper: float = 4.0,
) -> str:
    """判定单根 bar 所处阶段。优先级 S5 > S4 > S3 > S2 > S1。"""
    if pd.isna(r) or pd.isna(cv) or pd.isna(rs):
        return "S1"
    has_alignment = alignment in ("bull", "bear")
    if r > r_s5 and cv > cv_s5:
        return "S5"
    if r > r_s4 or rs >= rs_s4:
        return "S4"
    if has_alignment and r_s3_lower < r <= r_s3_upper and rs < rs_s4 and cv < cv_s3:
        return "S3"
    if has_alignment and r_s2_lower < r <= r_s2_upper:
        return "S2"
    return "S1"


def classify_stage_series(df: pd.DataFrame, **kwargs) -> pd.Series:
    """对整个 DataFrame 逐行判定阶段。"""
    stages = [
        classify_stage(r=row["r"], cv=row["cv"], rs=row["rs"],
                       alignment=row["alignment"], **kwargs)
        for _, row in df.iterrows()
    ]
    return pd.Series(stages, index=df.index, name="stage")


def is_downtrend(alignment: str) -> bool:
    """判断是否空头排列。"""
    return alignment == "bear"
