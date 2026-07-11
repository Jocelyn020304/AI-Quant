"""将 LaTeX 公式渲染为 PNG，使用 matplotlib 的 mathtext（兼容模式）"""
import re, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3\formula_imgs'
os.makedirs(OUT_DIR, exist_ok=True)

# 公式及其在 markdown 中出现的顺序（按块级先）
FORMULAS = [
    # (name, latex, display_mode, description)
    ('f01_sma', r'\mathrm{SMA}(N)_t = \frac{C_t + C_{t-1} + \cdots + C_{t-N+1}}{N}', True, 'SMA'),
    ('f02_ema', r'\mathrm{EMA}(N)_t = \alpha \cdot C_t + (1 - \alpha) \cdot \mathrm{EMA}(N)_{t-1}', True, 'EMA'),
    ('f03_alpha', r'\alpha = \frac{2}{N+1}', False, 'alpha公式'),
    ('f04_cumret', r'R_{\mathrm{cum}} = \frac{V_T - V_0}{V_0}', True, '累计回报'),
    ('f05_dd', r'D_t = \frac{V_t - \max_{0 \le s \le t} V_s}{\max_{0 \le s \le t} V_s}', True, '回撤'),
    ('f06_mdd', r'\mathrm{MDD} = \min_{0 \le t \le T} D_t', True, 'MDD'),
    ('f07_sharpe', r'\mathrm{Sharpe} = \frac{E(R_p) - R_f}{\sigma_p}', True, '夏普'),
    ('f08_mdd2', r'\mathrm{MDD} = \min_{0 \le t \le T} \frac{V_t - \max_{0 \le s \le t} V_s}{\max_{0 \le s \le t} V_s}', True, 'MDD详细'),
]

fig = plt.figure(figsize=(0.01, 0.01))
ax = fig.add_subplot(111)
ax.axis('off')

for name, latex, display, desc in FORMULAS:
    fig.clear()
    ax = fig.add_subplot(111)
    ax.axis('off')
    # mathtext 不支持 \dfrac, \text, \mathrm 中部分字符, \max, \min
    # \dfrac -> \frac
    # \max, \min -> 改为普通字符（mac 环境下可用）
    tex = latex
    tex = tex.replace('\\dfrac', '\\frac')
    # \mathrm{...} 已经支持
    # \max, \min: mathtext 支持 max, min（无反斜杠）
    # \le, \ge -> \leq, \geq
    tex = tex.replace('\\le', '\\leq').replace('\\ge', '\\geq')
    # 字号：匹配Word正文五号(10.5pt)，块级用10pt，行内用9pt
    fs = 10 if display else 9
    try:
        ax.text(0.5, 0.5, f'${tex}$', fontsize=fs, ha='center', va='center')
        out = os.path.join(OUT_DIR, f'{name}.png')
        fig.savefig(out, dpi=300, bbox_inches='tight', pad_inches=0.03, transparent=True)
        print(f'  ✅ {name} ({desc})')
    except Exception as e:
        print(f'  ⚠️ {name} 失败: {e}')

# 额外渲染行内公式
INLINE = [
    ('f_inline_alpha', r'\alpha = \frac{2}{N+1}', 'alpha'),
    ('f_inline_V0', r'V_0', 'V0'),
    ('f_inline_VT', r'V_T', 'VT'),
    ('f_inline_Vt', r'V_t', 'Vt'),
    ('f_inline_Dt', r'D_t', 'Dt'),
    ('f_inline_ERp', r'E(R_p)', 'ERp'),
    ('f_inline_Rf', r'R_f', 'Rf'),
    ('f_inline_sigmav3', r'R_f=2\%', 'Rf2'),
    ('f_inline_sigmap', r'\sigma_p', 'sigmap'),
]
for name, latex, desc in INLINE:
    fig.clear()
    ax = fig.add_subplot(111)
    ax.axis('off')
    tex = latex.replace('\\dfrac', '\\frac')
    try:
        ax.text(0.5, 0.5, f'${tex}$', fontsize=9, ha='center', va='center')
        out = os.path.join(OUT_DIR, f'{name}.png')
        fig.savefig(out, dpi=300, bbox_inches='tight', pad_inches=0.02, transparent=True)
        print(f'  ✅ {name} ({desc})')
    except Exception as e:
        print(f'  ⚠️ {name} 失败: {e}')

plt.close(fig)
print(f'\n图片已保存至：{OUT_DIR}')
