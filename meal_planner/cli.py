"""命令列預覽（讀取 SQLite 維護資料、更表、指標）。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meal_planner.dates_input import DateValidationError, cutoff_date, parse_date_expression
from meal_planner.excel_io import WorkbookValidationError
from meal_planner.preview import preview_days_with_cutoff


def _json_dump(payload: dict, *, pretty: bool) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def _error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def _success_payload(data: dict, debug: dict | None = None) -> dict:
    payload = {"ok": True, "data": data}
    if debug is not None:
        payload["debug"] = debug
    return payload


def _print_json(payload: dict, *, pretty: bool, stream=None) -> None:
    print(_json_dump(payload, pretty=pretty), file=stream or sys.stdout)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="餐單生成：預覽更表與營養指標（未含求解）")
    p.add_argument("--year", type=int, required=False)
    p.add_argument("--month", type=int, required=False)
    p.add_argument(
        "--dates",
        type=str,
        required=False,
        help='日期：空格分隔「3 5 7」或混範圍「12 13 14 15-17」、單段「12-15」、逗號多段「12-15,27-3」或「12,13,15-17」',
    )
    p.add_argument(
        "--skip-date-check",
        action="store_true",
        help="略過「早於界限日」拒絕（僅除錯用）",
    )
    p.add_argument(
        "--workbook",
        type=str,
        default=None,
        help="覆寫工作簿路徑（等同 MENU_WORKBOOK）",
    )
    p.add_argument(
        "--full-mode",
        action="store_true",
        help="使用完整求解模式（等同 API fast_mode=false）",
    )
    p.add_argument(
        "--reroll-nonce",
        type=int,
        default=0,
        help="覆寫配餐重抽 seed/nonce（等同 API reroll_nonce）",
    )
    p.add_argument(
        "--health",
        action="store_true",
        help="輸出 CLI/API 共用健康檢查資料後結束",
    )
    p.add_argument(
        "--cutoff",
        action="store_true",
        help="輸出目前日期拒絕界限後結束",
    )
    p.add_argument(
        "--debug-stats",
        action="store_true",
        help="在成功輸出加入 CLI 除錯統計（會自動使用 envelope 格式）",
    )
    p.add_argument(
        "--format",
        choices=("raw", "envelope"),
        default="raw",
        help="raw 保持舊 preview JSON；envelope 輸出 {ok,data/error,debug}，與 API error 形狀一致",
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help="輸出單行 JSON，方便 pipe 到其他工具",
    )
    args = p.parse_args(argv)
    started = time.perf_counter()
    pretty = not args.compact

    if args.workbook:
        import os

        os.environ["MENU_WORKBOOK"] = str(Path(args.workbook).expanduser())
        from meal_planner.settings import clear_settings_cache

        clear_settings_cache()

    from meal_planner.settings import get_settings

    wb_path = get_settings().workbook_path
    if args.health:
        _print_json(
            _success_payload(
                {
                    "status": "ok",
                    "primary_data_source": "sqlite",
                    "excel_role": "import_only",
                    "database": str(get_settings().database_path),
                    "database_exists": get_settings().database_path.is_file(),
                    "workbook": str(wb_path),
                    "workbook_exists": wb_path.is_file(),
                    "project_root": str(get_settings().project_root),
                }
            ),
            pretty=pretty,
        )
        return 0

    if args.cutoff:
        settings = get_settings()
        _print_json(
            _success_payload(
                {
                    "cutoff": cutoff_date(
                        settings.dates.timezone,
                        settings.dates.reject_days_before_today,
                    ).isoformat()
                }
            ),
            pretty=pretty,
        )
        return 0

    missing = [name for name in ("year", "month", "dates") if getattr(args, name) is None]
    if missing:
        _print_json(
            _error_payload(
                "validation_error",
                "Missing required arguments for preview",
                {"missing": [f"--{name.replace('_', '-')}" for name in missing]},
            ),
            pretty=pretty,
            stream=sys.stderr,
        )
        return 1

    try:
        dates = parse_date_expression(args.dates, year=args.year, month=args.month)
    except ValueError as e:
        _print_json(_error_payload("bad_request", str(e)), pretty=pretty, stream=sys.stderr)
        return 1

    try:
        out = preview_days_with_cutoff(
            dates,
            skip_date_validation=args.skip_date_check,
            reroll_nonce=args.reroll_nonce,
            fast_mode=not args.full_mode,
        )
    except DateValidationError as e:
        _print_json(
            _error_payload(
                "bad_request",
                str(e),
                {"rejected": [d.isoformat() for d in e.rejected_dates]},
            ),
            pretty=pretty,
            stream=sys.stderr,
        )
        return 1
    except WorkbookValidationError as e:
        _print_json(_error_payload("bad_request", str(e)), pretty=pretty, stream=sys.stderr)
        return 2
    except OSError as e:
        _print_json(
            _error_payload("internal_error", f"讀取資料失敗：{e}"),
            pretty=pretty,
            stream=sys.stderr,
        )
        return 2

    debug = None
    if args.debug_stats:
        debug = {
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "dates_count": len(dates),
            "workbook": str(wb_path),
            "fast_mode": not args.full_mode,
            "reroll_nonce": args.reroll_nonce,
        }
    if args.format == "envelope" or args.debug_stats:
        _print_json(_success_payload(out, debug), pretty=pretty)
    else:
        _print_json(out, pretty=pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
