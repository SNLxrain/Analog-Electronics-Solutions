# -*- coding: utf-8 -*-
"""
模板化验证：三个题型、四种学生解答场景
=========================================================
目的：证明「一个引擎 + N 个题型模板」这条路走得通，而不是每题写死一套代码。
"""

from verifier import verify, Step
import templates as T

MARK = {"ok": "✓ 正确", "approx": "△ 近似/精度问题", "calc": "✗ 计算执行错误",
        "wrong": "✗ 推导错误", "inherited": "⚠ 延续前面的错误",
        "bad_target": "✗ 目标量异常", "unparsable": "✗ 无法解析",
        "bad_symbol": "✗ 使用了不存在的量"}

ERROR_STATS = {}


def show(title, tpl, steps):
    print("=" * 78)
    print(f"场景：{title}")
    print(f"题型：{tpl.name}")
    print("=" * 78)
    print("SymPy 用电路方程独立求解的『真值』（判卷基准，不依赖任何模型输出）：")
    for k, v in tpl.truth.items():
        print(f"    {k:>4} = {float(v):>14.6g} {tpl.unit(k)}")

    report, first = verify(tpl, steps)
    print("\n逐步骤核验：")
    for v in report:
        print(f"\n  第 {v.n} 步  求 {v.target}　→　{MARK[v.status]}")
        print(f"     判定依据：{v.reason}")
        if v.error_type:
            print(f"     错因归类：{v.error_type}")
            ERROR_STATS[v.error_type] = ERROR_STATS.get(v.error_type, 0) + 1

    print("\n诊断结论：")
    if first:
        for v in report:
            if v.n == first:
                print(f"   ▶ 首次出错步骤：第 {first} 步（求 {v.target}）")
                print(f"   ▶ 错因：{v.error_type}")
    else:
        print("   ▶ 全部步骤通过，无错因")
    inh = [v.n for v in report if v.status == "inherited"]
    if inh:
        print(f"   ▶ 受前面错误牵连的步骤：{inh}（已去重，不重复计入错因）")
    print()


# ============================================================
# 场景 1：模板1 · 模电最经典的错误（漏掉 (1+β)Re）
# ============================================================
def scene1():
    tpl = T.tpl_ce_bias()
    steps = [
        Step(1, "Vbb", "Vcc*Rb2/(Rb1+Rb2)", 4.0),
        Step(2, "Rb",  "Rb1*Rb2/(Rb1+Rb2)", 6666.67),
        Step(3, "Ib",  "(Vbb-VBE)/(Rb+Re)", 4.3043e-4),          # ← 埋错：漏 (1+β)Re
        Step(4, "Ic",  "beta*Ib", 4.3043e-2),
        Step(5, "Vce", "Vcc-Ic*Rc-(1+beta)*Ib*Re", -117.56),
    ]
    show("学生把 (1+β)Re 漏了（经典错误）", tpl, steps)


# ============================================================
# 场景 2：模板2 · 一个"数值看不出、符号能看出"的错误 + 一个模型错误
# ============================================================
def scene2():
    tpl = T.tpl_ce_small_signal()
    steps = [
        # r_be 里把 (1+β) 写成 β：数值只差 0.8%，数值容差根本判不出来，但符号判定能抓住
        Step(1, "rbe", "rbb+beta*(26/1000)/IEQ", 1039.78),
        # 把 R_E 计入交流通路（忘记 C_E 旁路）
        Step(2, "Av",  "-beta*Rc/(rbe+Re)", -98.05),
        Step(3, "Ri",  "1/(1/Rb1+1/Rb2+1/rbe)", 899.5),
        Step(4, "Ro",  "Rc", 2000.0),                            # 不受前面错误影响
    ]
    show("符号层面的错误（数值只差 0.8%，容差判不出）＋ 交流通路画错", tpl, steps)


# ============================================================
# 场景 3：模板3 · 组态判断错误（同相放大误用反相公式）
# ============================================================
def scene3():
    tpl = T.tpl_opamp_two_stage()
    steps = [
        Step(1, "Av1", "-Rf1/R1", -10.0),
        Step(2, "vo1", "Av1*vi", -0.5),
        Step(3, "Av2", "-Rf2/R2", -9.0),        # ← 埋错：同相却用了反相公式
        Step(4, "vo",  "Av2*vo1", 4.5),
    ]
    show("同相放大器误用了反相公式", tpl, steps)


# ============================================================
# 场景 4：模板3 · 方法全对，只是算错（计算执行错误）
# ============================================================
def scene4():
    tpl = T.tpl_opamp_two_stage()
    steps = [
        Step(1, "Av1", "-Rf1/R1", -10.0),
        Step(2, "vo1", "Av1*vi", -0.5),
        Step(3, "Av2", "1+Rf2/R2", 10.0),
        Step(4, "vo",  "Av2*vo1", -6.0),        # ← 埋错：公式对，数值算成 -6.0
    ]
    show("表达式全对，只是数值算错（计算执行错误）", tpl, steps)


# ============================================================
# 场景 5：同一个学生答案，只是把老师认定的「可接受近似」放进白名单
#        —— 同一条判定，白名单一开一关，结论不同 → 说明这是个教师可控的开关
# ============================================================
def scene5():
    tpl = T.tpl_ce_small_signal(allow_beta_approx=True)
    steps = [
        Step(1, "rbe", "rbb+beta*(26/1000)/IEQ", 1039.78),   # 与场景2完全相同的答案
        Step(2, "Av",  "-beta*Rc/(rbe+Re)", -98.05),
        Step(3, "Ri",  "1/(1/Rb1+1/Rb2+1/rbe)", 899.5),
        Step(4, "Ro",  "Rc", 2000.0),
    ]
    show("同样的答案 + 近似白名单已启用（由老师决定）", tpl, steps)


if __name__ == "__main__":
    scene1()
    scene2()
    scene3()
    scene4()
    scene5()

    print("=" * 78)
    print("错因命中统计（本次演示）")
    print("=" * 78)
    for k, v in sorted(ERROR_STATS.items(), key=lambda x: -x[1]):
        print(f"   {k}：{v} 次")
    print("\n结论：同一个核验引擎 + 3 个题型模板，覆盖了 5 类错因的判定。")
