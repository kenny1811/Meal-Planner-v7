"""載入 config.yaml 與環境變數覆寫（規則.md §2）。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class WorkbookConfig:
    filename: str


@dataclass(frozen=True)
class SheetsConfig:
    menu_v5: str
    roster: str
    meal_times: str
    nutrition_list: str
    restaurant: str
    overtime: str
    schedule_grid: str
    payroll_times: str
    public_holidays: str


@dataclass(frozen=True)
class MenuV5LayoutConfig:
    indicator_header_row: int
    workday_indicator_row: int
    nonworkday_indicator_row: int
    nutrient_first_col: int
    nutrient_col_count: int


@dataclass(frozen=True)
class NutritionFormatConfig:
    tolerance: float
    kcal_per_fat_g: float
    fat_pct_total: float
    fat_pct_saturated: float
    fat_pct_trans: float


@dataclass(frozen=True)
class NutritionPortionConfig:
    default_g: float


@dataclass(frozen=True)
class RiceConfig:
    cooked_to_raw_brown: float
    cooked_to_raw_other: float
    water_multiplier: float
    rice_category_exact: str
    note_name_contains: tuple[str, ...]
    brown_name_contains: str


@dataclass(frozen=True)
class DatesConfig:
    reject_days_before_today: int
    timezone: str


@dataclass(frozen=True)
class PatternConfig:
    item_separator: str
    item_alt_separator: str


@dataclass(frozen=True)
class MealTimesStackConfig:
    """更碼以某前綴開頭時，四餐 Pattern 分別取自飯時指定「更碼」列（與 xlsm 2–5 行對齊）。"""

    enabled: bool
    roster_prefix: str
    pattern_rules: tuple[str, str, str, str]


@dataclass(frozen=True)
class MealBusinessRulesConfig:
    fixed_meals: tuple[str, ...]
    restaurant_lunch_workday_only: bool


@dataclass(frozen=True)
class OptimizerWeights:
    kcal: float = 1.0
    protein: float = 1.0
    carb: float = 1.0
    sugar: float = 0.5
    cholesterol: float = 0.5
    sodium: float = 0.5
    calcium: float = 1.0


@dataclass(frozen=True)
class OptimizerFatCapWeights:
    total: float = 50.0
    saturated: float = 10.0
    trans: float = 10.0


@dataclass(frozen=True)
class OptimizerConfig:
    band_delta_default: float
    weights: OptimizerWeights
    fat_cap_weights: OptimizerFatCapWeights
    replacement_search_enabled: bool = False
    auto_retry_enabled: bool = False
    relaxation_simulation_enabled: bool = False


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    workbook_path: Path
    database_path: Path
    sheets: SheetsConfig
    menu_v5_layout: MenuV5LayoutConfig
    nutrition_format: NutritionFormatConfig
    nutrition_portion: NutritionPortionConfig
    rice: RiceConfig
    dates: DatesConfig
    pattern: PatternConfig
    meal_times_stack: MealTimesStackConfig
    meal_business_rules: MealBusinessRulesConfig
    optimizer: OptimizerConfig


def _deep_get(d: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, Mapping) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _build_settings(project_root: Path, data: Mapping[str, Any]) -> AppSettings:
    wb_fn = str(data.get("workbook", {}).get("filename", "餐單AI版測試.xlsm"))
    workbook_path = (project_root / wb_fn).resolve()
    db_fn = str(data.get("database", {}).get("filename", "meal_planner.sqlite3"))
    database_path = (project_root / db_fn).resolve()

    sh = data.get("sheets", {}) or {}
    sheets = SheetsConfig(
        menu_v5=str(sh.get("menu_v5", "餐單v5")),
        roster=str(sh.get("roster", "更表")),
        meal_times=str(sh.get("meal_times", "飯時")),
        nutrition_list=str(sh.get("nutrition_list", "營養清單")),
        restaurant=str(sh.get("restaurant", "餐廳選擇")),
        overtime=str(sh.get("overtime", "加班表")),
        schedule_grid=str(sh.get("schedule_grid", "行位表")),
        payroll_times=str(sh.get("payroll_times", "更時表")),
        public_holidays=str(sh.get("public_holidays", "公眾假期")),
    )

    mv = data.get("menu_v5_layout", {}) or {}
    menu_v5_layout = MenuV5LayoutConfig(
        indicator_header_row=int(mv.get("indicator_header_row", 1)),
        workday_indicator_row=int(mv.get("workday_indicator_row", 2)),
        nonworkday_indicator_row=int(mv.get("nonworkday_indicator_row", 3)),
        nutrient_first_col=int(mv.get("nutrient_first_col", 6)),
        nutrient_col_count=int(mv.get("nutrient_col_count", 10)),
    )

    nf = data.get("nutrition_format", {}) or {}
    nutrition_format = NutritionFormatConfig(
        tolerance=float(nf.get("tolerance", 5)),
        kcal_per_fat_g=float(nf.get("kcal_per_fat_g", 9)),
        fat_pct_total=float(nf.get("fat_pct_total", 0.275)),
        fat_pct_saturated=float(nf.get("fat_pct_saturated", 0.07)),
        fat_pct_trans=float(nf.get("fat_pct_trans", 0.01)),
    )
    np = data.get("nutrition_portion", {}) or {}
    nutrition_portion = NutritionPortionConfig(
        default_g=float(np.get("default_g", 100)),
    )

    rc = data.get("rice", {}) or {}
    rice = RiceConfig(
        cooked_to_raw_brown=float(rc.get("cooked_to_raw_brown", 2.623)),
        cooked_to_raw_other=float(rc.get("cooked_to_raw_other", 2.67)),
        water_multiplier=float(rc.get("water_multiplier", 2)),
        rice_category_exact=str(rc.get("rice_category_exact", "米")),
        note_name_contains=tuple(
            str(x)
            for x in (
                rc.get("note_name_contains")
                if isinstance(rc.get("note_name_contains"), list)
                else ["米"]
            )
        ),
        brown_name_contains=str(rc.get("brown_name_contains", "糙米")),
    )

    dc = data.get("dates", {}) or {}
    dates = DatesConfig(
        reject_days_before_today=int(dc.get("reject_days_before_today", 6)),
        timezone=str(dc.get("timezone", "Asia/Hong_Kong")),
    )

    pc = data.get("pattern", {}) or {}
    pattern = PatternConfig(
        item_separator=str(pc.get("item_separator", "+")),
        item_alt_separator=str(pc.get("item_alt_separator", "/")),
    )

    mts = data.get("meal_times_stack", {}) or {}
    prules = mts.get("pattern_rules") or ["EleM", "IFCM*", "PenC*", "PenM"]
    if not isinstance(prules, list) or len(prules) != 4:
        prules = ["EleM", "IFCM*", "PenC*", "PenM"]
    meal_times_stack = MealTimesStackConfig(
        enabled=bool(mts.get("enabled", True)),
        roster_prefix=str(mts.get("roster_prefix", "Pen")),
        pattern_rules=tuple(str(x) for x in prules),
    )

    mbr = data.get("meal_business_rules", {}) or {}
    fixed_meals_raw = mbr.get("fixed_meals")
    fixed_meals = fixed_meals_raw if isinstance(fixed_meals_raw, list) else ["小食"]
    meal_business_rules = MealBusinessRulesConfig(
        fixed_meals=tuple(str(x) for x in fixed_meals),
        restaurant_lunch_workday_only=bool(mbr.get("restaurant_lunch_workday_only", True)),
    )

    oc = data.get("optimizer", {}) or {}
    ow = oc.get("weights", {}) or {}
    ofw = oc.get("fat_cap_weights", {}) or {}
    optimizer = OptimizerConfig(
        band_delta_default=float(oc.get("band_delta_default", 50)),
        weights=OptimizerWeights(
            kcal=float(ow.get("kcal", 1.0)),
            protein=float(ow.get("protein", 1.0)),
            carb=float(ow.get("carb", 1.0)),
            sugar=float(ow.get("sugar", 0.5)),
            cholesterol=float(ow.get("cholesterol", 0.5)),
            sodium=float(ow.get("sodium", 0.5)),
            calcium=float(ow.get("calcium", 1.0)),
        ),
        fat_cap_weights=OptimizerFatCapWeights(
            total=float(ofw.get("total", 50.0)),
            saturated=float(ofw.get("saturated", 10.0)),
            trans=float(ofw.get("trans", 10.0)),
        ),
        replacement_search_enabled=bool(oc.get("replacement_search_enabled", False)),
        auto_retry_enabled=bool(oc.get("auto_retry_enabled", False)),
        relaxation_simulation_enabled=bool(oc.get("relaxation_simulation_enabled", False)),
    )

    return AppSettings(
        project_root=project_root,
        workbook_path=workbook_path,
        database_path=database_path,
        sheets=sheets,
        menu_v5_layout=menu_v5_layout,
        nutrition_format=nutrition_format,
        nutrition_portion=nutrition_portion,
        rice=rice,
        dates=dates,
        pattern=pattern,
        meal_times_stack=meal_times_stack,
        meal_business_rules=meal_business_rules,
        optimizer=optimizer,
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    project_root = Path(os.environ.get("MENU_PROJECT_ROOT", _default_project_root())).resolve()
    cfg_path = Path(os.environ.get("MENU_CONFIG", str(project_root / "config.yaml")))
    data = _load_yaml_mapping(cfg_path)
    settings = _build_settings(project_root, data)

    wb_override = os.environ.get("MENU_WORKBOOK")
    db_override = os.environ.get("MENU_DATABASE")
    if wb_override or db_override:
        wb_path = Path(wb_override) if wb_override else settings.workbook_path
        workbook_path = wb_path if wb_path.is_absolute() else (project_root / wb_path).resolve()
        db_path = Path(db_override) if db_override else settings.database_path
        database_path = db_path if db_path.is_absolute() else (project_root / db_path).resolve()
        return AppSettings(
            project_root=settings.project_root,
            workbook_path=workbook_path,
            database_path=database_path,
            sheets=settings.sheets,
            menu_v5_layout=settings.menu_v5_layout,
            nutrition_format=settings.nutrition_format,
            nutrition_portion=settings.nutrition_portion,
            rice=settings.rice,
            dates=settings.dates,
            pattern=settings.pattern,
            meal_times_stack=settings.meal_times_stack,
            meal_business_rules=settings.meal_business_rules,
            optimizer=settings.optimizer,
        )
    return settings


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def save_rice_detail_settings(
    *,
    cooked_to_raw_brown: float,
    cooked_to_raw_other: float,
) -> AppSettings:
    """Persist editable rice conversion settings into config.yaml."""
    if cooked_to_raw_brown <= 0 or cooked_to_raw_other <= 0:
        raise ValueError("Rice cooked-to-raw ratios must be greater than zero.")

    settings = get_settings()
    cfg_path = Path(os.environ.get("MENU_CONFIG", str(settings.project_root / "config.yaml")))
    if not cfg_path.is_file():
        raise OSError(f"Cannot find config file: {cfg_path}")

    text = cfg_path.read_text(encoding="utf-8")

    def replace_key(src: str, key: str, value: float) -> str:
        pattern = rf"(^\s*{re.escape(key)}\s*:\s*)([-+]?\d+(?:\.\d+)?)(\s*(?:#.*)?$)"
        updated, count = re.subn(
            pattern,
            lambda m: f"{m.group(1)}{value:g}{m.group(3)}",
            src,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError(f"Cannot find rice setting {key} in config.yaml.")
        return updated

    text = replace_key(text, "cooked_to_raw_brown", cooked_to_raw_brown)
    text = replace_key(text, "cooked_to_raw_other", cooked_to_raw_other)
    cfg_path.write_text(text, encoding="utf-8", newline="\n")
    clear_settings_cache()
    return get_settings()
