"""测试所有块级公式的解析结果"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

GREEK = {'alpha':'α','beta':'β','sigma':'σ','mu':'μ','delta':'δ','theta':'θ','pi':'π'}
SYMS = {'cdot':'·','times':'×','cdots':'…','ldots':'…','leq':'≤','geq':'≥','le':'≤','ge':'≥','to':'→'}
TEXT_TAGS = ('mathrm', 'text', 'textbf', 'mathit', 'mathbf', 'operatorname')
SUB_MAP = {'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉',
           't':'ₜ','s':'ₛ','p':'ₚ','x':'ₓ','n':'ₙ','m':'ₘ','k':'ₖ','j':'ⱼ','i':'ᵢ'}
SUP_MAP = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹','T':'ᵀ','N':'ᴺ'}

def _find_matching_brace(s, start):
    depth = 1; i = start
    while i < len(s) and depth > 0:
        if s[i] == '{': depth += 1
        elif s[i] == '}': depth -= 1
        i += 1
    return i - 1

def _to_sub(text): return ''.join(SUB_MAP.get(c, c) for c in text)
def _to_sup(text): return ''.join(SUP_MAP.get(c, c) for c in text)

def _parse_latex(s):
    out = []; i = 0
    while i < len(s):
        ch = s[i]
        if ch == '\\':
            j = i + 1
            while j < len(s) and s[j].isalpha(): j += 1
            cmd = s[i+1:j]; i = j
            if cmd == 'frac':
                if i < len(s) and s[i] == ' ': i += 1
                num = ''
                if i < len(s) and s[i] == '{':
                    end = _find_matching_brace(s, i+1)
                    num = _parse_latex(s[i+1:end]); i = end + 1
                if i < len(s) and s[i] == '{':
                    end = _find_matching_brace(s, i+1)
                    den = _parse_latex(s[i+1:end]); i = end + 1
                else: den = ''
                out.append(f'({num})/({den})')
            elif cmd in TEXT_TAGS:
                if i < len(s) and s[i] == '{':
                    end = _find_matching_brace(s, i+1)
                    out.append(s[i+1:end]); i = end + 1
            elif cmd in GREEK: out.append(GREEK[cmd])
            elif cmd in SYMS: out.append(SYMS[cmd])
            elif cmd in ('max','min','sin','cos','log','ln'):
                if i < len(s) and s[i] == '_':
                    i += 1
                    if i < len(s) and s[i] == '{':
                        end = _find_matching_brace(s, i+1)
                        out.append(f'{cmd}_' + _to_sub(s[i+1:end])); i = end + 1
                    elif i < len(s): out.append(f'{cmd}_' + _to_sub(s[i])); i += 1
                else: out.append(cmd)
            else: out.append('\\' + cmd)
        elif ch == '^':
            i += 1
            if i < len(s) and s[i] == '{':
                end = _find_matching_brace(s, i+1)
                inner = _parse_latex(s[i+1:end]); i = end + 1
                out.append(_to_sup(inner))
            elif i < len(s): out.append(_to_sup(s[i])); i += 1
        elif ch == '_':
            i += 1
            if i < len(s) and s[i] == '{':
                end = _find_matching_brace(s, i+1)
                inner = _parse_latex(s[i+1:end]); i = end + 1
                out.append(_to_sub(inner))
            elif i < len(s): out.append(_to_sub(s[i])); i += 1
        elif ch == '{':
            end = _find_matching_brace(s, i+1)
            out.append(_parse_latex(s[i+1:end])); i = end + 1
        elif ch == ' ':
            if out and not out[-1].endswith(' '): out.append(' ')
            i += 1
        else: out.append(ch); i += 1
    return ''.join(out)

def latex_to_unicode(latex): return _parse_latex(latex.strip())

tests = [
    (r'\mathrm{SMA}(N)_t = \frac{C_t + C_{t-1} + \cdots + C_{t-N+1}}{N}',
     'SMA(N)ₜ = (Cₜ + Cₜ₋₁ + … + Cₜ₋ₙ₊₁)/(N)'),
    (r'\mathrm{EMA}(N)_t = \alpha \cdot C_t + (1 - \alpha) \cdot \mathrm{EMA}(N)_{t-1}',
     'EMA(N)ₜ = α · Cₜ + (1 - α) · EMA(N)ₜ₋₁'),
    (r'\alpha = \frac{2}{N+1}',
     'α = (2)/(N+1)'),
    (r'R_{\mathrm{cumulative}} = \frac{V_T - V_0}{V_0}',
     'Rcumulative = (V_T - V₀)/(V₀)'),
    (r'D_t = \frac{V_t - \max_{0 \leq s \leq t} V_s}{\max_{0 \leq s \leq t} V_s}',
     'Dₜ = (Vₜ - max_0 ≤ s ≤ t Vₛ)/(max_0 ≤ s ≤ t Vₛ)'),
    (r'\mathrm{MDD} = \min_{0 \leq t \leq T} D_t',
     'MDD = min_0 ≤ t ≤ T Dₜ'),
    (r'\mathrm{Sharpe Ratio} = \frac{E(R_p) - R_f}{\sigma_p}',
     'Sharpe Ratio = (E(Rₚ) - Rf)/(σₚ)'),
    (r'\mathrm{MDD} = \min_{0 \leq t \leq T} \frac{V_t - \max_{0 \leq s \leq t} V_s}{\max_{0 \leq s \leq t} V_s}',
     'MDD = min_0 ≤ t ≤ T (Vₜ - max_0 ≤ s ≤ t Vₛ)/(max_0 ≤ s ≤ t Vₛ)'),
]

all_ok = True
for inp, expected in tests:
    result = latex_to_unicode(inp)
    status = '✅' if result == expected else '❌'
    if result != expected: all_ok = False
    print(f'{status} IN:  {inp}')
    print(f'  OUT: {result}')
    print(f'  EXP: {expected}')
    print()

print(f'总计 {len(tests)} 个公式，{"全部正确 ✅" if all_ok else "存在差异 ❌"}')
