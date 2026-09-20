# -*- coding: utf-8 -*-
"""
核验引擎（可复用）
=========================================================
把「逐步骤核验」抽象成通用能力：题型只需提供
  · 基本参数符号与取值
  · 标准解法的【分步符号定义】（canon，按依赖顺序）
  · 常见错误模式库（patterns）
  · 物理合理性检查（sanity）
即可获得：逐步判定 + 首次出错定位 + 错因归类。

双模式核验（本项目的一个关键设计）：
  模式A 用「真值」判定这一步本身对不对；
  模式B 用「学生自己的前置结果」判断后续步骤是"又错了"还是"只是继承了前面的错"。
"""

from dataclasses import dataclass
import sympy as sp

TOL_STRICT = 0.01   # ≤1%      → 判对
TOL_LOOSE = 0.10    # 1%~10%   → "近似/精度问题"，交教师确认
                    # >10%     → 判错


@dataclass
class Step:
    """学生（或大模型）的一步声明"""
    n: int
    target: str      # 这一步求什么量
    expr: str        # 用什么表达式
    value: float     # 算出多少


@dataclass
class Verdict:
    n: int
    target: str
    status: str      # ok / approx / calc / wrong / inherited / bad_target / unparsable / bad_symbol
    reason: str
    error_type: str = ""


def _num(x):
    """把 sympy 表达式转成 float；若仍含自由符号或无法求值，返回 None"""
    if x is None:
        return None
    try:
        x = sp.N(x)
    except Exception:
        return None
    if getattr(x, "free_symbols", None):
        return None
    try:
        return float(x)
    except Exception:
        return None


def _inline(expr, defs):
    """把派生量递归展开成基本参数（canon 是 DAG，必然终止）"""
    for _ in range(len(defs) + 2):
        new = expr.subs(defs)
        if new == expr:
            break
        expr = new
    return expr


class ProblemTemplate:
    def __init__(self, name, symbols, params, canon, units=None,
                 patterns=None, sanity=None, whitelist=None):
        self.name = name
        self.symbols = dict(symbols)
        self.params = dict(params)
        self.canon = dict(canon)                 # 有序 dict：必须按依赖顺序排列
        self.units = units or {}
        self.patterns = patterns or []
        self.sanity = sanity or {}
        # 近似白名单：命中则判对（由任课老师决定哪些近似可接受）
        self.whitelist = whitelist or []
        # 派生量（= 解题步骤的目标量）当作符号，用于解析学生表达式
        self.derived = {k: sp.Symbol(k) for k in self.canon}
        self.syms = {**self.symbols, **self.derived}
        self.truth = self._solve_truth()

    # ---------- 真值：按依赖顺序代入求解（不依赖任何模型输出） ----------
    def _solve_truth(self):
        truth = {}
        for k, expr in self.canon.items():
            sub = {**self.params, **{self.derived[j]: truth[j] for j in truth}}
            truth[k] = sp.N(expr.subs(sub))
        return truth

    def unit(self, k):
        return self.units.get(k, "")

    def parse(self, s):
        return sp.sympify(s, locals=self.syms)

    def find_pattern(self, expr):
        for pat, etype, why in self.patterns:
            if sp.simplify(expr - pat) == 0:
                return etype, why
        return None

    def hit_whitelist(self, expr):
        for pat, why in self.whitelist:
            if sp.simplify(expr - pat) == 0:
                return why
        return None

    def equivalent(self, expr, target):
        """符号级等价判定。

        关键点：标准解法里的 Ie 与学生写下的 (1+β)Ib 是同一个量，只是写法不同。
        所以两边都**递归展开成基本参数**后再比较——既不受书写形式影响，
        也不受"是否把中间量内联展开"影响。
        """
        defs = {self.derived[k]: self.canon[k] for k in self.canon if k != target}
        return sp.simplify(_inline(expr, defs) - _inline(self.canon[target], defs)) == 0

    # ---------- 单个步骤的判定 ----------
    def judge(self, st, expr, equiv, rel, self_ok, first_error):
        t, unit = st.target, self.unit(st.target)

        # 1) 继承前面的错误（方法无误 + 自己算得自洽 + 但因前置结果偏离而偏离）
        if first_error is not None and st.n > first_error and equiv and self_ok and rel > TOL_STRICT:
            return Verdict(st.n, t, "inherited",
                           f"本步方法无误，但因第 {first_error} 步结果已偏离，本步随之偏离标准值 "
                           f"{float(self.truth[t]):.4g}{unit}；不计入错因统计")

        # 2) 方法对 + 数值对
        if equiv and rel <= TOL_STRICT:
            return Verdict(st.n, t, "ok", "表达式与标准解法等价，数值一致")

        # 3) 方法对 + 数值在近似带
        if equiv and rel <= TOL_LOOSE:
            return Verdict(st.n, t, "approx",
                           f"表达式正确，但与标准值偏差 {rel*100:.1f}%，属常见教材近似，"
                           f"需教师确认是否接受")

        # 4) 方法对 + 数值错 → 计算执行错误
        if equiv:
            return Verdict(st.n, t, "calc",
                           f"表达式正确，但数值应为 {float(self.truth[t]):.4g}{unit}，"
                           f"声明为 {st.value:.4g}{unit}（偏差 {rel*100:.1f}%）",
                           "计算执行错误")

        # 5) 方法错 → 先查近似白名单（老师认定可接受的近似），再查错误模式库
        wl = self.hit_whitelist(expr)
        if wl:
            return Verdict(st.n, t, "approx",
                           f"命中『近似白名单』（{wl}）→ 判对；数值偏差 {rel*100:.2f}%")

        hit = self.find_pattern(expr)
        if hit:
            etype, why = hit
        else:
            etype, why = "电路模型/公式选择错误", "未命中已知错误模式，需人工复核（错误模式库可扩充）"
        extra = ""
        if rel <= TOL_STRICT:
            extra = f"（数值偏差仅 {rel*100:.2f}%，仅符号层面不等价）"
        return Verdict(st.n, t, "wrong", why + extra, etype)


def verify(tpl, steps):
    """返回 (报告列表, 首次出错步骤号)"""
    report, first_error, student_env = [], None, {}

    for st in steps:
        unit = tpl.unit(st.target)

        # 目标量不在标准解法里
        if st.target not in tpl.canon:
            report.append(Verdict(st.n, st.target, "bad_target",
                                  "这一步在求一个标准解法里不存在的量 → 可能是分析方法选择错误",
                                  "分析方法选择错误"))
            first_error = first_error or st.n
            continue

        # 解析表达式
        try:
            expr = tpl.parse(st.expr)
        except Exception as ex:
            report.append(Verdict(st.n, st.target, "unparsable",
                                  f"表达式无法解析：{ex}", "公式/符号代入错误"))
            first_error = first_error or st.n
            continue

        # 用到了标准解法里不存在的符号（自造变量）
        unknown = expr.free_symbols - set(tpl.syms.values())
        if unknown:
            report.append(Verdict(st.n, st.target, "bad_symbol",
                                  f"表达式里出现了标准解法中不存在的量：{', '.join(str(u) for u in unknown)}",
                                  "电路模型建立错误"))
            first_error = first_error or st.n
            student_env[tpl.derived[st.target]] = st.value
            continue

        # ---- 符号级等价判定（递归展开成基本参数后比较，不受书写形式影响）----
        equiv = tpl.equivalent(expr, st.target)

        # ---- 模式A：用真值核验 ----
        val_truth = _num(expr.subs({**tpl.params,
                                    **{tpl.derived[k]: tpl.truth[k] for k in tpl.truth}}))
        truth_v = float(tpl.truth[st.target])
        rel_expr = (abs(val_truth - truth_v) / max(abs(truth_v), 1e-12)) \
            if val_truth is not None else float("inf")
        # 同时看"学生实际写下的数值"偏了多少——判卷要看的是学生答了什么
        rel_decl = abs(st.value - truth_v) / max(abs(truth_v), 1e-12)
        rel = max(rel_expr, rel_decl)

        # ---- 模式B：用学生自己的前置结果核验 ----
        val_self = _num(expr.subs({**tpl.params, **student_env})) if student_env else None
        self_ok = (val_self is not None and
                   abs(val_self - st.value) / max(abs(st.value), 1e-12) < 0.02)

        v = tpl.judge(st, expr, equiv, rel, self_ok, first_error)

        # ---- 物理合理性检查（工作区、相位等）：仅在方法本身没错时才提示，避免噪音 ----
        if st.target in tpl.sanity and v.status in ("ok", "approx"):
            pred, msg = tpl.sanity[st.target]
            if not pred(st.value):
                v.reason += f"　⚠ 合理性检查：{msg}（声明值 {st.value:.4g}{unit}）"

        report.append(v)
        if v.status in ("wrong", "calc", "bad_target", "unparsable", "bad_symbol") and first_error is None:
            first_error = st.n
        student_env[tpl.derived[st.target]] = st.value

    return report, first_error
