"""LaTeX → Unicode 文本（V2 修复版）"""
import re

GREEK = {'alpha':'α','beta':'β','sigma':'σ','mu':'μ','delta':'δ','theta':'θ','pi':'π'}
SYMS = {'cdot':'·','times':'×','cdots':'…','ldots':'…',
        'leq':'≤','geq':'≥','le':'≤','ge':'≥','to':'→',
        'infty':'∞','partial':'∂','sum':'Σ','prod':'Π','int':'∫',
        'neq':'≠','approx':'≈','sim':'~'}
TEXT_TAGS = ('mathrm', 'text', 'textbf', 'mathit', 'mathbf', 'operatorname')

SUB = {'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅',
       '6':'₆','7':'₇','8':'₈','9':'₉',
       't':'ₜ','s':'ₛ','p':'ₚ','x':'ₓ','n':'ₙ','m':'ₘ',
       'k':'ₖ','j':'ⱼ','i':'ᵢ'}
SUP = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵',
       '6':'⁶','7':'⁷','8':'⁸','9':'⁹','T':'ᵀ','N':'ᴺ'}


def find_matching_brace(s, start):
    """找到从start位置开始的匹配右花括号"""
    depth = 1
    i = start
    while i < len(s) and depth > 0:
        if s[i] == '{': depth += 1
        elif s[i] == '}': depth -= 1
        i += 1
    return i - 1  # 结束位置（含右括号）


def latex_to_unicode(latex):
    s = latex.strip()
    return _parse(s)


def _parse(s):
    """核心解析：处理 \command{X}{Y} 和文本"""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]

        if ch == '\\':
            # 命令
            j = i + 1
            while j < len(s) and s[j].isalpha():
                j += 1
            cmd = s[i+1:j]
            i = j

            if cmd == 'frac':
                # \frac{X}{Y} - 读取两个参数
                if i < len(s) and s[i] == ' ':
                    i += 1
                if i < len(s) and s[i] == '{':
                    end = find_matching_brace(s, i+1)
                    num = _parse(s[i+1:end])
                    i = end + 1
                else:
                    num = ''; 
                if i < len(s) and s[i] == '{':
                    end = find_matching_brace(s, i+1)
                    den = _parse(s[i+1:end])
                    i = end + 1
                else:
                    den = ''
                out.append(f'({num})/({den})')
            elif cmd in TEXT_TAGS:
                if i < len(s) and s[i] == '{':
                    end = find_matching_brace(s, i+1)
                    out.append(s[i+1:end])  # 不递归，直接保留文本
                    i = end + 1
            elif cmd in GREEK:
                out.append(GREEK[cmd])
            elif cmd in SYMS:
                out.append(SYMS[cmd])
            elif cmd == 'max' or cmd == 'min':
                # 处理 max_{...} 或 min_{...}
                if i < len(s) and s[i] == '_':
                    i += 1
                    if i < len(s) and s[i] == '{':
                        end = find_matching_brace(s, i+1)
                        out.append(cmd + '_' + s[i+1:end])
                        i = end + 1
                    else:
                        out.append(cmd + '_')
                else:
                    out.append(cmd)
            elif cmd in ('sum', 'prod', 'int'):
                out.append({'sum':'Σ','prod':'Π','int':'∫'}[cmd])
            else:
                out.append('\\' + cmd)

        elif ch == '^':
            # 上标
            i += 1
            if i < len(s) and s[i] == '{':
                end = find_matching_brace(s, i+1)
                sup_text = s[i+1:end]
                i = end + 1
            else:
                sup_text = s[i] if i < len(s) else ''
                i += 1
            out.append(_to_sup(sup_text))
        elif ch == '_':
            # 下标
            i += 1
            if i < len(s) and s[i] == '{':
                end = find_matching_brace(s, i+1)
                sub_text = s[i+1:end]
                i = end + 1
            else:
                sub_text = s[i] if i < len(s) else ''
                i += 1
            out.append(_to_sub(sub_text))
        elif ch == '{':
            end = find_matching_brace(s, i+1)
            inner = _parse(s[i+1:end])
            out.append(inner)
            i = end + 1
        elif ch == ' ':
            # 保留有意义空格
            if out and not out[-1].endswith(' '):
                out.append(' ')
            i += 1
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _to_sub(text):
    """转换为Unicode下标"""
    return ''.join(SUB.get(c, c) for c in text)


def _to_sup(text):
    """转换为Unicode上标"""
    return ''.join(SUP.get(c, c) for c in text)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    tests = [
        r'\mathrm{SMA}(N)_t = \frac{C_t + C_{t-1} + \cdots + C_{t-N+1}}{N}',
        r'\mathrm{EMA}(N)_t = \alpha \cdot C_t + (1 - \alpha) \cdot \mathrm{EMA}(N)_{t-1}',
        r'\alpha = \frac{2}{N+1}',
        r'R_{\mathrm{cumulative}} = \frac{V_T - V_0}{V_0}',
        r'D_t = \frac{V_t - \max_{0 \leq s \leq t} V_s}{\max_{0 \leq s \leq t} V_s}',
        r'\mathrm{MDD} = \min_{0 \leq t \leq T} D_t',
        r'\mathrm{Sharpe Ratio} = \frac{E(R_p) - R_f}{\sigma_p}',
        r'\mathrm{MDD} = \min_{0 \leq t \leq T} \frac{V_t - \max_{0 \leq s \leq t} V_s}{\max_{0 \leq s \leq t} V_s}',
    ]
    for t in tests:
        print('IN: ', t)
        print('OUT:', latex_to_unicode(t))
        print()
