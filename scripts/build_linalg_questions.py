"""Generate data/courses/linalg/questions.json: 12 parameterised question types x 8 instances.

Answers are computed with exact Fraction arithmetic; distractors come from typical mistakes (wrong order, sign,
forgetting to divide). Like the high-school bank these are verifiable templates, not 96 independent problems.
Questions reference knowledge points by slug; scripts/import_course.py maps slugs to course knowledge ids.
"""
import json
from fractions import Fraction as F
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'data' / 'courses' / 'linalg' / 'questions.json'
SOURCE = '知序自编线性代数参数化题库 v1'

def fmt(x):
    x = F(x)
    return str(x.numerator) if x.denominator == 1 else f'{x.numerator}/{x.denominator}'

def mat(rows):
    return r'\begin{pmatrix}' + r'\\'.join('&'.join(fmt(v) for v in r) for r in rows) + r'\end{pmatrix}'

def det2(m):
    return F(m[0][0]) * m[1][1] - F(m[0][1]) * m[1][0]

def det3(m):
    a, b, c = m
    return (F(a[0]) * b[1] * c[2] + F(a[1]) * b[2] * c[0] + F(a[2]) * b[0] * c[1]
            - F(a[2]) * b[1] * c[0] - F(a[0]) * b[2] * c[1] - F(a[1]) * b[0] * c[2])

def rank(rows):
    m = [[F(v) for v in r] for r in rows]; r = 0
    for col in range(len(m[0])):
        pivot = next((i for i in range(r, len(m)) if m[i][col] != 0), None)
        if pivot is None:
            continue
        m[r], m[pivot] = m[pivot], m[r]
        for i in range(len(m)):
            if i != r and m[i][col] != 0:
                f = m[i][col] / m[r][col]
                m[i] = [a - f * b for a, b in zip(m[i], m[r])]
        r += 1
    return r

def options(i, correct, wrong):
    """Four distinct options; the correct one rotates through positions so answers are not guessable by place."""
    correct = fmt(correct) if not isinstance(correct, str) else correct
    seen, rest = {correct}, []
    for w in list(wrong) + [F(correct) + k for k in (1, -1, 2, -2, 3)] if not isinstance(correct, str) or correct.lstrip('-').replace('/', '').isdigit() else wrong:
        w = fmt(w) if not isinstance(w, str) else w
        if w not in seen:
            seen.add(w); rest.append(w)
        if len(rest) == 3:
            break
    assert len(rest) == 3, (correct, wrong)
    pos = i % 4
    return rest[:pos] + [correct] + rest[pos:], pos

def q(slug, i, stem, correct, wrong, explanation, difficulty=1):
    opts, answer = options(i, correct, wrong)
    return dict(knowledge=slug, stem=stem, options=opts, answer=answer, explanation=explanation, difficulty=difficulty, source=SOURCE)

def vectors(i):
    u, v, k = (i + 1, 2 - i), (3, i - 1), 2 + i % 2
    comp = i % 2
    val = k * u[comp] + v[comp]
    return q('vectors', i, f'设 $\\mathbf{{u}}=({u[0]},{u[1]})$，$\\mathbf{{v}}=({v[0]},{v[1]})$，求 ${k}\\mathbf{{u}}+\\mathbf{{v}}$ 的第 {comp + 1} 个分量。',
             val, [u[comp] + k * v[comp], k * u[comp] - v[comp], k * u[1 - comp] + v[1 - comp]],
             f'线性运算逐分量进行：第 {comp + 1} 个分量为 ${k}\\times({u[comp]})+({v[comp]})={val}$。', 1 + (i >= 4))

def dot_product(i):
    if i % 2 == 0:
        u, v = (1 + i // 2, -1, 2), (2, 3, i // 2 + 1)
        val = sum(a * b for a, b in zip(u, v))
        return q('dot_product', i, f'计算内积 $({u[0]},{u[1]},{u[2]})\\cdot({v[0]},{v[1]},{v[2]})$。', val,
                 [u[0] * v[0], sum(u) + sum(v), -val],
                 f'对应分量相乘再相加：${u[0]}\\cdot{v[0]}+({u[1]})\\cdot{v[1]}+{u[2]}\\cdot{v[2]}={val}$。结果是数，不是向量。')
    a, b, c = 2 + i // 2, 1 + i % 3, -1
    k = F(-(a + 2 * c), b)
    return q('dot_product', i, f'当 $k$ 为何值时，$(1,k,2)$ 与 $({a},{b},{c})$ 正交？', k, [-k, F(a + 2 * c), F(a - 2, b)],
             f'正交即内积为零：${a}+{b}k+2\\times({c})=0$，解得 $k={fmt(k)}$。', 2)

def matrix_ops(i):
    A, B = [[1, i % 3 + 1], [2, -1]], [[i + 1, 0], [1, 2]]
    ab = A[0][0] * B[0][1] + A[0][1] * B[1][1]
    ba = B[0][0] * A[0][1] + B[0][1] * A[1][1]
    return q('matrix_ops', i, f'设 $A={mat(A)}$，$B={mat(B)}$，求 $AB$ 第 1 行第 2 列的元素。', ab,
             [ba, A[0][1] * B[0][1], A[0][1] + B[0][1]],
             f'$(AB)_{{12}}$ 是 $A$ 的第 1 行与 $B$ 的第 2 列的内积：${A[0][0]}\\cdot{B[0][1]}+{A[0][1]}\\cdot{B[1][1]}={ab}$。注意 $AB\\ne BA$。', 1 + (i >= 4))

def determinant(i):
    if i % 2 == 0:
        m = [[i + 2, 3], [1, i // 2 + 2]]
        d = det2(m)
        return q('determinant', i, f'计算二阶行列式 $\\begin{{vmatrix}}{m[0][0]}&{m[0][1]}\\\\{m[1][0]}&{m[1][1]}\\end{{vmatrix}}$。', d,
                 [F(m[0][0]) * m[1][1] + m[0][1] * m[1][0], -d, F(m[0][1]) * m[1][0] - F(m[0][0]) * m[1][1] + 1],
                 f'主对角线乘积减副对角线乘积：${m[0][0]}\\times{m[1][1]}-{m[0][1]}\\times{m[1][0]}={fmt(d)}$。')
    m = [[1, 2, 0], [0, i // 2 + 1, 3], [2, 0, 1]]
    d = det3(m)
    return q('determinant', i, f'计算三阶行列式 $\\det{mat(m)}$。', d, [-d, d + 2, F(m[0][0]) * m[1][1] * m[2][2]],
             f'按对角线法则：$1\\cdot{m[1][1]}\\cdot1+2\\cdot3\\cdot2+0-0-1\\cdot3\\cdot0-2\\cdot0\\cdot1={fmt(d)}$。', 2)

def matrix_inverse(i):
    a, b = i + 2, 1
    c, d = 2 * i + 3, 2           # det = 2(i+2) - (2i+3) = 1, so the inverse has integer entries
    detv = det2([[a, b], [c, d]])
    entry = (i % 2)
    val = F(d, 1) / detv if entry == 0 else F(-b, 1) / detv
    label = '第 1 行第 1 列' if entry == 0 else '第 1 行第 2 列'
    return q('matrix_inverse', i, f'设 $A={mat([[a, b], [c, d]])}$，求 $A^{{-1}}$ {label}的元素。', val,
             [a, -val, b if entry else -d],
             f'$\\det A={a}\\cdot{d}-{b}\\cdot{c}={fmt(detv)}$，$A^{{-1}}=\\frac{{1}}{{\\det A}}\\begin{{pmatrix}}d&-b\\\\-c&a\\end{{pmatrix}}$，所求元素为 {fmt(val)}。', 1 + (i >= 4))

def gaussian_elimination(i):
    x0, y0 = i % 4 + 1, 2 - i // 2
    a1, b1, a2, b2 = 1, 1, 2, -1 - i % 2
    c1, c2 = a1 * x0 + b1 * y0, a2 * x0 + b2 * y0
    coef = '-' if b2 == -1 else f'{b2:+}'
    return q('gaussian_elimination', i, f'用消元法解方程组 $\\begin{{cases}}x+y={c1}\\\\2x{coef}y={c2}\\end{{cases}}$，求 $x$。', x0,
             [y0, -x0, c1],
             f'第二个方程减去第一个方程的 2 倍消去 $x$，得 $y={y0}$，回代得 $x={c1}-({y0})={x0}$。可代回原方程检验。')

def matrix_rank(i):
    r = [1, 2, 3, 2, 1, 3, 2, 3][i]
    p, s = i % 3 + 1, i % 2 + 2
    if r == 1:
        rows = [[1, p, 2], [2, 2 * p, 4], [s, s * p, 2 * s]]
    elif r == 2:
        rows = [[1, p, 0], [0, 1, s], [1, p + 1, s]]
    else:
        rows = [[1, p, 0], [0, 1, s], [1, 0, 1]]
    assert rank(rows) == r
    return q('rank', i, f'求矩阵 ${mat(rows)}$ 的秩。', str(r), [str(x) for x in (0, 1, 2, 3) if x != r],
             '用初等行变换化为行阶梯形，非零行个数即秩。' + ('后两行都是第一行的倍数。' if r == 1 else '第三行等于前两行之和。' if r == 2 else '行列式不为零，矩阵满秩。'), 1 + (r == 2))

def solution_structure(i):
    if i % 2 == 0:
        n, r = 3 + i // 2, 1 + i // 4
        return q('solution_structure', i, f'{n} 元齐次线性方程组 $A\\mathbf{{x}}=\\mathbf{{0}}$ 中 $r(A)={r}$，其基础解系含几个向量？', n - r,
                 [r, n, n - r + 1], f'解空间维数为 $n-r={n}-{r}={n - r}$，基础解系含 {n - r} 个线性无关解。')
    kinds = [('r(A)=2,\\ r([A\\mid\\mathbf{b}])=3', 3, '无解', 'r(A)<r([A|b])，方程组无解。'),
             ('r(A)=r([A\\mid\\mathbf{b}])=3', 3, '唯一解', '有解且 r(A) 等于未知数个数 3，解唯一。'),
             ('r(A)=r([A\\mid\\mathbf{b}])=2', 3, '无穷多解', '有解且 r(A)=2<3，有无穷多解。'),
             ('r(A)=r([A\\mid\\mathbf{b}])=4', 4, '唯一解', '有解且 r(A) 等于未知数个数 4，解唯一。')]
    cond, n, ans, why = kinds[i // 2]
    return q('solution_structure', i, f'{n} 元线性方程组 $A\\mathbf{{x}}=\\mathbf{{b}}$ 满足 ${cond}$，它的解的情况是？', ans,
             [x for x in ('无解', '唯一解', '无穷多解', '恰有两个解') if x != ans], why + '线性方程组不会恰好有两个解。', 2)

def linear_independence(i):
    if i % 2 == 0:
        a, b = i // 2 + 2, i // 2 + 1
        k = 2 * b
        return q('linear_independence', i, f'当 $k$ 为何值时，向量 $(1,{a},{b})$ 与 $(2,{2 * a},k)$ 线性相关？', k, [b, k + 1, -k],
                 f'两个向量线性相关当且仅当成比例。第二个向量的前两个分量是第一个的 2 倍，所以 $k=2\\times{b}={k}$。')
    m, n = [(4, 3), (2, 3), (3, 2), (5, 4)][i // 2]
    ans = '一定线性相关' if m > n else '不能确定，需要计算'
    return q('linear_independence', i, f'$\\mathbb{{R}}^{n}$ 中任取 {m} 个向量，它们是否线性相关？', ans,
             [x for x in ('一定线性相关', '一定线性无关', '不能确定，需要计算', '一定构成一组基') if x != ans],
             f'$\\mathbb{{R}}^{n}$ 中多于 {n} 个的向量必线性相关；不超过 {n} 个时要用秩判断。', 2)

def basis_dimension(i):
    p = i % 3 + 1
    if i % 3 == 0:
        vs, r = [(1, 0, p), (0, 1, 1), (1, 1, p + 1)], 2
    elif i % 3 == 1:
        vs, r = [(1, p, 0), (2, 2 * p, 0), (3, 3 * p, 0)], 1
    else:
        vs, r = [(1, 0, 0), (0, 1, p), (0, 0, 1)], 3
    assert rank(vs) == r
    vec = '、'.join(f'$({a},{b},{c})$' for a, b, c in vs)
    return q('basis_dimension', i, f'向量 {vec} 张成的空间维数是多少？', str(r), [str(x) for x in (0, 1, 2, 3) if x != r],
             f'张成空间的维数等于以这些向量为列的矩阵的秩，此处秩为 {r}。' + ('第三个向量是前两个之和。' if r == 2 else '三个向量互相成比例。' if r == 1 else ''), 1 + (r == 2))

def eigen(i):
    if i % 2 == 0:
        d1, d2, x = i // 2 + 1, -(i // 2) - 2, i + 3
        m = [[d1, x], [0, d2]]
        return q('eigen', i, f'以下哪一个是矩阵 ${mat(m)}$ 的特征值？', d2, [x, d1 + d2, -d2],
                 f'上三角矩阵的特征值是主对角线元素 {d1} 和 {d2}。')
    m = [[i + 1, 2], [1, 3]]
    if i % 4 == 1:
        val, what, why = m[0][0] + m[1][1], '之和', '特征值之和等于迹'
        wrong = [det2(m), m[0][0] * m[1][1], -val]
    else:
        val, what, why = det2(m), '之积', '特征值之积等于行列式'
        wrong = [m[0][0] + m[1][1], m[0][0] * m[1][1], -val]
    return q('eigen', i, f'矩阵 ${mat(m)}$ 的全部特征值{what}是多少？', val, wrong, f'{why}，结果为 {fmt(val)}，无需求出每个特征值。', 2)

def diagonalization(i):
    if i % 2 == 0:
        l1, l2, k = i // 2 + 1, -1, 2 + i % 4 // 2
        val = l1 ** k + l2 ** k
        return q('diagonalization', i, f'2 阶矩阵 $A$ 的特征值为 {l1} 和 {l2}，求 $A^{k}$ 的迹。', val, [(l1 + l2) ** k, l1 + l2, l1 ** k - l2 ** k],
                 f'$A^{k}$ 的特征值为 ${l1}^{k}$ 与 $({l2})^{k}$，迹等于特征值之和：{val}。注意不是 $(\\operatorname{{tr}}A)^{k}$。', 2)
    cases = [('3 阶矩阵有 3 个互不相同的特征值', '一定可以对角化'),
             ('3 阶矩阵有一个二重特征值', '不能确定，需检查线性无关特征向量的个数'),
             ('4 阶矩阵有 4 个线性无关的特征向量', '一定可以对角化'),
             ('2 阶矩阵 $\\begin{pmatrix}1&1\\\\0&1\\end{pmatrix}$', '不可以对角化')]
    cond, ans = cases[i // 2]
    why = {'一定可以对角化': '有 n 个线性无关的特征向量（互异特征值的特征向量线性无关）即可对角化。',
           '不能确定，需检查线性无关特征向量的个数': '有重特征值时可能可对角化也可能不可以。',
           '不可以对角化': '特征值 1 是二重的，但 $(I-A)\\mathbf{x}=\\mathbf{0}$ 的基础解系只有 1 个向量。'}[ans]
    return q('diagonalization', i, f'{cond}，它能否相似对角化？', ans,
             [x for x in ('一定可以对角化', '不可以对角化', '不能确定，需检查线性无关特征向量的个数', '只有对称矩阵才能对角化') if x != ans], why, 2)

GENERATORS = [vectors, dot_product, matrix_ops, determinant, matrix_inverse, gaussian_elimination,
              matrix_rank, solution_structure, linear_independence, basis_dimension, eigen, diagonalization]

def build():
    items = [g(i) for g in GENERATORS for i in range(8)]
    for it in items:
        assert len(it['options']) == 4 and len(set(it['options'])) == 4, it
        assert 0 <= it['answer'] <= 3 and it['difficulty'] in (1, 2, 3)
    return items

if __name__ == '__main__':
    items = build()
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'wrote {len(items)} questions to {OUT}')
