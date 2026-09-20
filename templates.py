# -*- coding: utf-8 -*-
"""
三个题型模板
=========================================================
模板化的核心主张：**每种题型只写一次"标准解法的分步符号定义"，
剩下的核验、错因判定、物理检查全部复用引擎。**

模板1  分压式共射 · 静态工作点        （纯直流，线性方程组）
模板2  共射 · 小信号等效（Re 被旁路）  （含器件模型，符号化简）
模板3  两级集成运放 · 虚短虚断        （多级级联，组态判断）
"""

import sympy as sp
from verifier import ProblemTemplate


# ============================================================
# 模板 1：分压式共射放大电路 · 静态工作点
# ============================================================
def tpl_ce_bias():
    Vcc, Rb1, Rb2, Rc, Re, VBE, beta = sp.symbols(
        'Vcc Rb1 Rb2 Rc Re VBE beta', positive=True)
    D = {k: sp.Symbol(k) for k in ["Vbb", "Rb", "Ib", "Ic", "Ie", "Vb", "Vce"]}

    # 标准解法：分步符号定义（必须按依赖顺序）
    canon = {
        "Vbb": Vcc * Rb2 / (Rb1 + Rb2),
        "Rb":  Rb1 * Rb2 / (Rb1 + Rb2),
        "Ib":  (D["Vbb"] - VBE) / (D["Rb"] + (1 + beta) * Re),
        "Ic":  beta * D["Ib"],
        "Ie":  (1 + beta) * D["Ib"],
        "Vb":  D["Vbb"] - D["Ib"] * D["Rb"],
        "Vce": Vcc - D["Ic"] * Rc - D["Ie"] * Re,
    }

    patterns = [
        ((D["Vbb"] - VBE) / (D["Rb"] + Re), "近似条件误用",
         "忽略了射极电阻反射到基极的 (1+β)Re"),
        (D["Vbb"] / (D["Rb"] + (1 + beta) * Re), "近似条件误用",
         "漏掉了 VBE（把 V_B 直接当成 Vbb）"),
        ((D["Vbb"] - VBE) / (D["Rb"] + beta * Re), "公式/符号代入错误",
         "把 (1+β) 写成了 β"),
    ]
    sanity = {
        "Vce": (lambda v: v > 0.7,
                "V_CE 低于 0.7V，三极管已进入饱和区，静态工作点不合理"),
    }
    return ProblemTemplate(
        "分压式共射 · 静态工作点",
        dict(Vcc=Vcc, Rb1=Rb1, Rb2=Rb2, Rc=Rc, Re=Re, VBE=VBE, beta=beta),
        {Vcc: 12, Rb1: 20000, Rb2: 10000, Rc: 2000, Re: 1000,
         VBE: sp.Rational(7, 10), beta: 100},
        canon,
        units={"Vbb": "V", "Rb": "Ω", "Ib": "A", "Ic": "A",
               "Ie": "A", "Vb": "V", "Vce": "V"},
        patterns=patterns, sanity=sanity)


# ============================================================
# 模板 2：共射放大电路 · 小信号等效（R_E 被 C_E 交流旁路）
# ============================================================
def tpl_ce_small_signal(allow_beta_approx=False):
    rbb, beta, IEQ, Rc, Rb1, Rb2, Re = sp.symbols(
        'rbb beta IEQ Rc Rb1 Rb2 Re', positive=True)
    D = {k: sp.Symbol(k) for k in ["rbe", "Av", "Ri", "Ro"]}
    UT = sp.Rational(26, 1000)          # 26 mV

    canon = {
        "rbe": rbb + (1 + beta) * UT / IEQ,          # 26mV / I_EQ(A)
        "Av":  -beta * Rc / D["rbe"],
        "Ri":  1 / (1 / Rb1 + 1 / Rb2 + 1 / D["rbe"]),
        "Ro":  Rc,
    }

    patterns = [
        (-beta * Rc / (D["rbe"] + Re), "电路模型建立错误",
         "把 R_E 计入了交流通路（有旁路电容 C_E 时，R_E 在交流上应被短路）"),
        (1 / (1 / Rb1 + 1 / Rb2), "电路模型建立错误",
         "交流输入电阻漏掉了 r_be"),
        (rbb + beta * UT / IEQ, "公式/符号代入错误",
         "r_be 公式里的 (1+β) 写成了 β"),
        (beta * Rc / D["rbe"], "公式/符号代入错误",
         "共射放大器增益漏掉负号（输出与输入反相）"),
    ]
    sanity = {
        "Av": (lambda v: v < 0, "共射放大器输出与输入反相，增益应为负值"),
    }
    # 近似白名单由任课老师决定：β≫1 时把 (1+β) 记作 β，是否算可接受近似
    whitelist = []
    if allow_beta_approx:
        whitelist = [(rbb + beta * UT / IEQ,
                      "β≫1 时 r_be 中把 (1+β) 记作 β，属课程可接受的近似")]
    return ProblemTemplate(
        "共射 · 小信号等效（Re 被旁路）" + ("〔近似白名单已启用〕" if allow_beta_approx else ""),
        dict(rbb=rbb, beta=beta, IEQ=IEQ, Rc=Rc, Rb1=Rb1, Rb2=Rb2, Re=Re),
        {rbb: 200, beta: 100, IEQ: 0.00309605, Rc: 2000,
         Rb1: 20000, Rb2: 10000, Re: 1000},
        canon,
        units={"rbe": "Ω", "Av": "倍", "Ri": "Ω", "Ro": "Ω"},
        patterns=patterns, sanity=sanity, whitelist=whitelist)


# ============================================================
# 模板 3：两级集成运放 · 虚短虚断
# ============================================================
def tpl_opamp_two_stage():
    R1, Rf1, R2, Rf2, vi = sp.symbols('R1 Rf1 R2 Rf2 vi', positive=True)
    D = {k: sp.Symbol(k) for k in ["Av1", "vo1", "Av2", "vo"]}

    canon = {
        "Av1": -Rf1 / R1,                 # 第一级：反相放大
        "vo1": D["Av1"] * vi,
        "Av2": 1 + Rf2 / R2,              # 第二级：同相放大
        "vo":  D["Av2"] * D["vo1"],
    }

    patterns = [
        (Rf1 / R1, "公式/符号代入错误",
         "反相放大器增益漏掉负号"),
        (1 + Rf1 / R1, "电路模型建立错误",
         "反相放大器误用了同相公式（应为 -Rf/R1）"),
        (-Rf2 / R2, "电路模型建立错误",
         "同相放大器误用了反相公式（应为 1+Rf/R2）"),
    ]
    return ProblemTemplate(
        "两级集成运放 · 虚短虚断",
        dict(R1=R1, Rf1=Rf1, R2=R2, Rf2=Rf2, vi=vi),
        {R1: 10000, Rf1: 100000, R2: 10000, Rf2: 90000, vi: sp.Rational(1, 20)},
        canon,
        units={"Av1": "倍", "vo1": "V", "Av2": "倍", "vo": "V"},
        patterns=patterns)


ALL = [tpl_ce_bias, tpl_ce_small_signal, tpl_opamp_two_stage]
