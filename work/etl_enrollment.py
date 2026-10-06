# /// script
# requires-python = ">=3.10"
# dependencies = ["xlrd>=2.0"]
# ///
"""
把東華大學 114-1 在學生人數統計表（.xls）轉成整齊的 CSV。

用法：
  uv run work/etl_enrollment.py
輸出：
  work/enrollment_114-1.csv（UTF-8 with BOM）
  每列：college, dept_raw, program_raw, gender, count
"""
import csv
import re
import sys
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "東華大學統計資料" / "在學人數統計表"
OUT = ROOT / "work" / "enrollment_114-1.csv"

# 欄位位置（第 2、3 列是表頭）
COL_PROGRAM, COL_COLLEGE, COL_DEPT, COL_GROUP = 0, 1, 2, 3
COL_TOTAL_F, COL_TOTAL_M = 5, 6  # 「總計」底下的女、男

# 「X 合計N」區段標題 → 標準學制名稱
PROGRAMS = {"博士班": "博士班", "碩士班": "碩士班", "碩專班": "碩士在職專班", "學士班": "學士班"}


def text(v) -> str:
    return str(v).strip() if v != "" else ""


def strip_note(s: str) -> str:
    """去掉括號裡的註記：「環境暨海洋學院(111更名 )」→「環境暨海洋學院」"""
    return re.sub(r"[（(].*?[)）]", "", s).strip()


def fill_merged(sh, col: int) -> list[str]:
    """讀出一欄的值；合併儲存格只有第一格有字，把它填到整個合併範圍。"""
    vals = [text(sh.cell_value(r, col)) for r in range(sh.nrows)]
    in_merge = [False] * sh.nrows
    for r0, r1, c0, c1 in sh.merged_cells:
        if c0 <= col < c1:
            for r in range(r0, r1):
                vals[r] = vals[r0]
                in_merge[r] = True
    return vals, in_merge


def common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def main():
    src = next(SRC_DIR.glob("114-1*.xls"))
    wb = xlrd.open_workbook(src, formatting_info=True)  # formatting_info 才拿得到合併儲存格
    sh = wb.sheet_by_index(0)

    colleges, _ = fill_merged(sh, COL_COLLEGE)
    depts, dept_merged = fill_merged(sh, COL_DEPT)
    groups = [text(sh.cell_value(r, COL_GROUP)) for r in range(sh.nrows)]

    # 備註以下全部不要
    end = next((r for r in range(sh.nrows) if text(sh.cell_value(r, 0)).startswith("備註")), sh.nrows)

    rows = []  # (row_index, program)
    program = None
    for r in range(3, end):
        head = text(sh.cell_value(r, COL_PROGRAM))
        if "合計" in head or "總計" in head:
            key = head.split()[0]
            program = PROGRAMS.get(key)  # 「總計=1+2+3+4」不是學制，得到 None
            continue
        if program is None or sh.cell_value(r, COL_TOTAL_F) == "":
            continue
        rows.append((r, program))

    # 系所欄空白、又不在任何合併範圍裡的列（例：物理系「應用物理博士班一般組」），
    # 報表上視覺上屬於相鄰的系所。往上、往下各找一個有系所名的鄰列，
    # 選「分組」名稱開頭最相像的那一邊。
    for r, _ in rows:
        if depts[r] or dept_merged[r]:
            continue
        up = next((u for u in range(r - 1, 2, -1) if depts[u]), None)
        down = next((d for d in range(r + 1, end) if depts[d]), None)
        cands = [c for c in (up, down) if c is not None]
        best = max(cands, key=lambda c: common_prefix(groups[r], groups[c]))
        print(f"⚠️ 第 {r + 1} 列「{groups[r]}」系所欄空白且未合併，歸給「{depts[best]}」", file=sys.stderr)
        depts[r] = depts[best]

    # 同一系所、同一學制的多個分組加總成一列（保留第一次出現的順序）
    totals: dict[tuple[str, str, str], list[int]] = {}
    for r, program in rows:
        key = (strip_note(colleges[r]), depts[r], program)
        f = int(sh.cell_value(r, COL_TOTAL_F) or 0)
        m = int(sh.cell_value(r, COL_TOTAL_M) or 0)
        acc = totals.setdefault(key, [0, 0])
        acc[0] += f
        acc[1] += m

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["college", "dept_raw", "program_raw", "gender", "count"])
        for (college, dept, program), (f, m) in totals.items():
            w.writerow([college, dept, program, "女", f])
            w.writerow([college, dept, program, "男", m])

    grand = sum(f + m for f, m in totals.values())
    print(f"✅ {src.name} → {OUT.relative_to(ROOT)}：{len(totals) * 2} 列，總人數 {grand}")


if __name__ == "__main__":
    main()
