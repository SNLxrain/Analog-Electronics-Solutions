# -*- coding: utf-8 -*-
"""
M0 spike ① 最小可行原型
=========================================================
目标：证明「SymPy 独立求解 + 逐步骤核验 + 错因规则化判定」这条路走得通。

示例题型：分压式共射放大电路 · 静态工作点计算（模电最经典的入门题）

核心思想（三句话）：
  1. 我们不训练模型去"看懂"电路；我们把电路写成**方程**，交给 SymPy 解 → 得到"真值"；
  2. 学生/模型的每一步都声明「这一步求什么量、用什么表达式、算出多少」→ 逐量核验；
  3. 核验结果用**规则**映射到错因类别 → 错因判定可复现、可评测，而不是让模型猜。
"""

import sympy as sp

TOL_STRICT = 0.01   # 1% 以内 → 判对
TOL_LOOSE = 0.10    # 1%~10% → "近似/精度问题"，需老师确认是否可接受
                    # >10%  → 判错

# ============================================================
# 一、用电路方程独立求解 —— 这就是"真值"，不依赖任何模型输出
# ============================================================
def build_ground_truth():
    Vcc, Rb1, Rb2, Rc, Re, VBE, beta = sp.symbols(
        'Vcc Rb1 Rb2 Rc Re VBE beta', positive=True)
    params = {Vcc: 12, Rb1: 20000, Rb2: 10000, Rc: 2000, Re: 1000,
              VBE: sp.Rational(7, 10), beta: 100}

    # 直流通路：基极用戴维南等效
    Rb = Rb1 * Rb2 / (Rb1 + Rb2)              # 基极等效电阻
    Vbb = Vcc * Rb2 / (Rb1 + Rb2)             # 基极等效电源
    Ib = (Vbb - VBE) / (Rb + (1 + beta) * Re)  # 关键：(1+β)Re 是射极电阻反射到基极的等效
    Ie = (1 + beta) * Ib
    Ic = beta * Ib
    Vb = Vbb - Ib * Rb
    Vce = Vcc - Ic * Rc - Ie * Re

    canon = {"Rb": Rb, "Vbb": Vbb, "Ib": Ib, "Ic": Ic, "Ie": Ie, "Vb": Vb, "Vce": Vce}
    units = {"Rb": "Ω", "Vbb": "V", "Ib": "A", "Ic": "A", "Ie": "A", "Vb": "V", "Vce": "V"}
    truth = {k: sp.N(v.subs(params)) for k, v in canon.items()}
    base = {s.name: s for s in (Vcc, Rb1, Rb2, Rc, Re, VBE, beta)}
    return base, params, canon, truth, units


# ============================================================
# 二、错因规则表 —— 把"常见错误表达式"映射到错因类别
#    这是"错因可复现"的关键：不是模型猜，是规则判
# ============================================================
def classify_formula_error(expr_student, target, canon, syms):
    e = sp.simplify(expr_student - canon[target])
    if e == 0:
        return None

    # 常见错误模式库（可持续扩充，并由老师补充判据）
    # 注意：必须复用同一批符号对象，否则 Re 与 Re(positive=True) 会被当成两个不同的量
    Vbb, VBE, Rb, Re = syms["Vbb"], syms["VBE"], syms["Rb"], syms["Re"]
    beta = syms["beta"]
    patterns = [
        ((Vbb - VBE) / (Rb + Re),
         "近似条件误用：忽略了射极电阻反射到基极的 (1+β)Re"),
        (Vbb / (Rb + (1 + beta) * Re),
         "近似条件误用：漏掉了 VBE（把 V_B 直接当成 Vbb）"),
        ((Vbb - VBE) / (Rb + beta * Re),
         "公式/符号代入错误：把 (1+β) 写成了 β"),
    ]
    for pat, why in patterns:
        if sp.simplify(expr_student - pat) == 0:
            return why
    return "电路模型/公式选择错误（未命中已知错误模式，需人工复核）"


# ============================================================
# 三、逐步骤核验 + 首次出错定位
# ============================================================
def diagnose(steps, base, params, canon, truth, units):
    derived = {k: sp.Symbol(k) for k in canon}          # 派生量当作符号
    syms_all = {**base, **derived}                      # 统一符号表（必须复用同一批对象）

    report = []
    first_error = None
    student_env = {}      # 学生已经算出来的结果（用于判断"继承错误"）

    for st in steps:
        target, expr_str, declared = st["target"], st["expr"], st["value"]

        if target not in canon:
            report.append((st["n"], target, "✗ 目标量异常", "分析方法选择错误：这一步在求一个不该求/不存在的量"))
            first_error = first_error or st["n"]
            continue

        # --- 解析学生的表达式 ---
        try:
            expr_sym = sp.sympify(expr_str, locals=syms_all)
        except Exception as ex:
            report.append((st["n"], target, "✗ 无法解析", f"表达式解析失败：{ex}"))
            first_error = first_error or st["n"]
            continue

        # --- 核验 1：表达式本身与标准解法是否等价（模式 A：用真值） ---
        equiv = sp.simplify(expr_sym - canon[target]) == 0
        val_truth = sp.N(expr_sym.subs({**params,
                    **{derived[k]: truth[k] for k in truth}}))

        # --- 核验 2：学生这一步自己算得自洽吗（模式 B：用他自己的前置结果） ---
        env = {**params, **student_env}
        val_self = sp.N(expr_sym.subs(env)) if env else None

        rel = abs(float(val_truth - truth[target])) / max(abs(float(truth[target])), 1e-12)

        # --- 先判断：这一步是不是"延续前面的错误"（自己推导自洽，只是继承了前面偏掉的结果）---
        inherited = (first_error is not None and st["n"] > first_error and val_self is not None and
                     abs(float(val_self) - float(declared)) /
                     max(abs(float(declared)), 1e-12) < 0.02)

        if inherited:
            verdict = "⚠ 延续前面的错误"
            reason = (f"本步推导方式本身无误，但因第 {first_error} 步结果已偏离，"
                      f"本步随之偏离标准值 {float(truth[target]):.4g}{units[target]}；"
                      f"不计入错因统计")
        elif equiv and rel <= TOL_STRICT:
            verdict, reason = "✓ 正确", "表达式与标准解法等价，数值一致"
        elif equiv and rel <= TOL_LOOSE:
            verdict = "△ 近似/精度问题"
            reason = (f"表达式正确，但与标准值偏差 {rel*100:.1f}%，"
                      f"属于常见教材近似，需教师确认是否接受")
        elif equiv:
            verdict, reason = "✗ 计算执行错误", (
                f"表达式正确，但数值应为 {float(truth[target]):.4g}{units[target]}，"
                f"声明为 {declared:.4g}{units[target]}（偏差 {rel*100:.1f}%）")
        else:
            why = classify_formula_error(expr_sym, target, canon, syms_all)
            verdict, reason = "✗ 推导错误", why

        report.append((st["n"], target, verdict, reason))

        if "✗" in verdict and first_error is None:
            first_error = st["n"]

        student_env[derived[target]] = declared

    return report, first_error


# ============================================================
# 四、跑一个真实的学生解答（第 3 步是模电最经典的错误）
# ============================================================
def main():
    base, params, canon, truth, units = build_ground_truth()

    print("=" * 74)
    print("【第一步】SymPy 用电路方程独立求出的『真值』（这是判卷基准）")
    print("=" * 74)
    for k in ["Rb", "Vbb", "Ib", "Ic", "Vce"]:
        print(f"   {k:>4} = {float(truth[k]):>14.6g} {units[k]}")

    steps = [
        {"n": 1, "target": "Vbb", "expr": "Vcc*Rb2/(Rb1+Rb2)",      "value": 4.0},
        {"n": 2, "target": "Rb",  "expr": "Rb1*Rb2/(Rb1+Rb2)",      "value": 6666.67},
        {"n": 3, "target": "Ib",  "expr": "(Vbb-VBE)/(Rb+Re)",      "value": 4.3043e-4},
        {"n": 4, "target": "Ic",  "expr": "beta*Ib",                "value": 4.3043e-2},
        {"n": 5, "target": "Vce", "expr": "Vcc-Ic*Rc-(1+beta)*Ib*Re", "value": -117.56},
    ]

    print()
    print("=" * 74)
    print("【第二步】逐步骤核验（学生的解答里埋了模电最经典的一个错误）")
    print("=" * 74)
    report, first_error = diagnose(steps, base, params, canon, truth, units)
    for n, target, verdict, reason in report:
        print(f"\n  第 {n} 步  求 {target}")
        print(f"     {verdict}")
        print(f"     判定依据：{reason}")

    print()
    print("=" * 74)
    print("【第三步】诊断结论")
    print("=" * 74)
    if first_error:
        print(f"   ▶ 首次出错步骤：第 {first_error} 步")
        for n, target, verdict, reason in report:
            if n == first_error:
                print(f"   ▶ 错因：{reason}")
        print("   ▶ 后续步骤标记为『受前面错误影响』，不重复计入错因")
    else:
        print("   ▶ 全部步骤通过")


if __name__ == "__main__":
    main()
