# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas"]
# ///
"""
把 data/ 裡的三個 CSV 整理成網頁可直接載入的 docs/data.js。

用法：
  uv run work/build_data.py

docs/index.html 用 <script src="data.js"></script> 載入後，資料在 window.NDHU_DATA。
雙擊開啟（file://）時瀏覽器不允許 fetch CSV，所以把資料包成 .js。

為了讓檔案小一點：
- 先依網頁會用到的欄位加總（休學資料不分身份類別）
- 文字欄位改成代碼：每列存的是 semesters / colleges / depts / degrees / genders / reasons 的索引
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data.js"

DEGREE_ORDER = ["學士", "碩士", "博士"]
GENDER_ORDER = ["女", "男"]


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def main():
    enr = read("enrollment.csv")
    leave = read("leave.csv")
    mapping = read("dept_mapping.csv")
    enr["count"] = enr["count"].astype(int)
    for c in ("new_leave", "on_leave_end"):
        leave[c] = leave[c].astype(int)

    # 只保留網頁會用到的欄位並加總
    enr_keys = ["semester", "college", "dept", "degree", "gender"]
    enr_g = enr.groupby(enr_keys, as_index=False)["count"].sum()
    leave_keys = enr_keys + ["reason"]
    leave_g = leave.groupby(leave_keys, as_index=False)[["new_leave", "on_leave_end"]].sum()
    leave_g = leave_g[(leave_g.new_leave > 0) | (leave_g.on_leave_end > 0)]

    # 代碼表
    semesters = sorted(set(enr.semester) | set(leave.semester))
    colleges = sorted(set(mapping.college) | set(enr.college) | set(leave.college))
    dept_names = sorted(set(mapping.dept) | set(enr.dept) | set(leave.dept))
    missing = set(enr.dept) | set(leave.dept)
    missing -= set(mapping.dept)
    if missing:
        raise SystemExit(f"❌ 這些系所不在 dept_mapping.csv：{sorted(missing)}")
    m = mapping.set_index("dept")
    depts = [
        {
            "name": d,
            "college": m.loc[d, "college"],
            "aliases": [a.strip() for a in m.loc[d, "aliases"].split(";") if a.strip()],
        }
        for d in dept_names
    ]
    reason_group = leave.drop_duplicates("reason").set_index("reason")["reason_group"]
    reasons = [{"name": r, "group": reason_group[r]}
               for r in sorted(reason_group.index, key=lambda r: (reason_group[r] != "自請休學", r))]

    idx = {
        "semester": {v: i for i, v in enumerate(semesters)},
        "college": {v: i for i, v in enumerate(colleges)},
        "dept": {v: i for i, v in enumerate(dept_names)},
        "degree": {v: i for i, v in enumerate(DEGREE_ORDER)},
        "gender": {v: i for i, v in enumerate(GENDER_ORDER)},
        "reason": {r["name"]: i for i, r in enumerate(reasons)},
    }

    def encode(df, keys, values):
        return [[idx[k][row[k]] for k in keys] + [int(row[v]) for v in values]
                for row in df.to_dict("records")]

    payload = {
        "generated": date.today().isoformat(),
        "note": "rows 內的文字欄位是對應清單的索引；college 以 114-1 組織為準",
        "semesters": semesters,
        "colleges": colleges,
        "depts": depts,
        "degrees": DEGREE_ORDER,
        "genders": GENDER_ORDER,
        "reasons": reasons,
        "enrollment": {"fields": enr_keys + ["count"],
                       "rows": encode(enr_g, enr_keys, ["count"])},
        "leave": {"fields": leave_keys + ["new_leave", "on_leave_end"],
                  "rows": encode(leave_g, leave_keys, ["new_leave", "on_leave_end"])},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(f"// 由 work/build_data.py 產生，請勿手動修改\nwindow.NDHU_DATA={body};\n", encoding="utf-8")

    # 核對：加總前後總數一致，114-1 在學人數 = 10035
    assert enr_g["count"].sum() == enr["count"].sum()
    assert leave_g.new_leave.sum() == leave.new_leave.sum()
    assert leave_g.on_leave_end.sum() == leave.on_leave_end.sum()
    total_1141 = int(enr_g.loc[enr_g.semester == "114-1", "count"].sum())
    print(f"{'✅' if total_1141 == 10035 else '❌'} 114-1 在學人數合計：{total_1141}（應為 10035）")
    print(f"✅ {OUT.relative_to(ROOT)}：{OUT.stat().st_size / 1024:.1f} KB；"
          f"在學 {len(enr)}→{len(enr_g)} 列，休學 {len(leave)}→{len(leave_g)} 列，"
          f"{len(semesters)} 學期、{len(colleges)} 學院、{len(depts)} 系所、{len(reasons)} 種休學原因")
    if total_1141 != 10035:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
