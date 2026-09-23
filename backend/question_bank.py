"""Original demonstration items; parameterized families have an independent numerical audit."""
KNOWLEDGE = [
    ('sets', '集合与逻辑', '集合运算', [], '用交、并、补描述集合之间的关系。'),
    ('domain', '函数基础', '函数定义域', ['sets'], '先检查分母、偶次根式和对数的限制，再取交集。'),
    ('evaluation', '函数基础', '函数求值', ['domain'], '识别自变量和对应关系，代入后按运算顺序求值。'),
    ('monotonicity', '函数性质', '函数单调性', ['evaluation'], '理解区间上的增减变化，结合函数表达式判断。'),
    ('parity', '函数性质', '函数奇偶性', ['evaluation'], '先检查定义域关于原点对称，再比较 f(-x) 与 f(x)。'),
    ('quadratic', '函数模型', '二次函数', ['monotonicity'], '配方求顶点，结合区间分析最值。'),
    ('exponential', '函数模型', '指数函数', ['monotonicity'], '理解指数运算与指数函数的单调性。'),
    ('logarithm', '函数模型', '对数函数', ['exponential', 'domain'], '把对数关系还原为指数关系，并检查真数为正。'),
    ('derivative_definition', '导数基础', '导数定义', ['monotonicity'], '用差商极限理解某点处的瞬时变化率。'),
    ('derivative_rules', '导数基础', '导数计算', ['derivative_definition'], '运用幂函数求导及和、差、常数倍法则。'),
    ('tangent', '导数应用', '切线方程', ['derivative_rules', 'evaluation'], '先求切点与切线斜率，再写点斜式方程。'),
    ('derivative_monotonicity', '导数应用', '导数与单调性', ['derivative_rules', 'monotonicity'], '根据导数符号划分原函数的单调区间。'),
    ('extrema', '导数应用', '函数极值', ['derivative_monotonicity'], '结合驻点两侧的导数符号变化判断极值。'),
    ('optimization', '导数应用', '闭区间最值', ['extrema', 'quadratic'], '比较区间端点与区间内驻点的函数值。'),
]

def items():
    result = []
    def add(kid, i, stem, value, explanation, wrong=None):
        values = [str(value)] + ([str(v) for v in wrong] if wrong else [str(value+1), str(value-1), str(value+2)])
        assert len(set(values)) == 4
        shift = i % 4
        values = values[shift:] + values[:shift]
        result.append(dict(knowledge_id=kid, auxiliary_ids=[], stem=stem, options=values,
                           answer=(-shift) % 4, explanation=explanation,
                           difficulty=1 if i <= 5 else (2 if i <= 8 else 3),
                           source='原创演示题 · 参数化数学练习，非官方真题', active=True))
    # Ten distinct questions per node, including five basic items to make passing possible.
    for i in range(1, 11):
        n = i + 1
        add('sets', i, f'集合 A={{1,2,…,{n+2}}}，B={{{n},{n+1},…,{2*n+2}}}，A∩B 的元素个数为多少？', 3,
            f'公共元素是 {n}、{n+1}、{n+2}，所以有 3 个元素。', [2,4,n+4])
        add('domain', i, f'函数 $f(x)=\\sqrt{{x-{n}}}$ 的定义域为 $[a,+\\infty)$，a 等于多少？', n,
            f'被开方数要求 x−{n}≥0，因此 x≥{n}，a={n}。')
        add('evaluation', i, f'已知 $f(x)=x^2+{n}x$，求 $f({n})$。', 2*n*n,
            f'代入 x={n}，得到 {n}²+{n}×{n}={2*n*n}。')
        add('monotonicity', i, f'函数 $f(x)=({n}-a)x+1$ 在实数集上严格递增。以下 a 的值哪一个符合条件？', n-1,
            f'斜率 {n}−a>0，即 a<{n}；四个选项中只有 {n-1} 符合。', [n,n+1,n+2])
        add('parity', i, f'函数 $f(x)=x^3+ax^2+{n}x$ 为奇函数，a 应为多少？', 0,
            '定义域为实数集，f(−x)=−f(x) 要求偶次项系数为 0，所以 a=0。', [n,-n,1])
        add('quadratic', i, f'函数 $f(x)=x^2-{2*n}x+{n*n+3}$ 在实数集上的最小值为多少？', 3,
            f'配方得到 f(x)=(x−{n})²+3，平方项非负，最小值为 3。', [n*n+3,-3,0])
        add('exponential', i, f'若 $2^x={2**n}$，则 x 为多少？', n,
            f'{2**n}=2 的 {n} 次方，指数函数严格单调，因此 x={n}。')
        add('logarithm', i, f'计算 $\\log_2 {2**n}$。', n,
            f'因为 2 的 {n} 次方等于 {2**n}，根据对数定义可得结果为 {n}。')
        add('derivative_definition', i, f'设 $f(x)=x^2$，求 $\\lim_{{h\\to0}}\\frac{{f({n}+h)-f({n})}}{{h}}$。', 2*n,
            f'差商为 [({n}+h)²−{n}²]/h={2*n}+h，h 趋于 0 时极限为 {2*n}。')
        add('derivative_rules', i, f'函数 $f(x)=x^3+{n}x^2$，求 $f\'(1)$。', 3+2*n,
            f'导函数为 f′(x)=3x²+{2*n}x，代入 x=1 得 {3+2*n}。')
        add('tangent', i, f'曲线 $y=x^2$ 在点 $({n},{n*n})$ 处的切线写成 $y=kx+b$，b 为多少？', -n*n,
            f'斜率 k=2×{n}={2*n}，点斜式 y−{n*n}={2*n}(x−{n})，故 b={-n*n}。')
        add('derivative_monotonicity', i, f'函数 $f(x)=x^2-{2*n}x$ 的严格递增区间为 $[a,+\\infty)$，a 的最小值为多少？', n,
            f'f′(x)=2x−{2*n}，x>{n} 时为正，函数在 [{n},+∞) 上严格递增，最小边界 a={n}。')
        add('extrema', i, f'函数 $f(x)=x^3-{3*n*n}x$ 的极小值点的横坐标是多少？', n,
            f'f′(x)=3(x−{n})(x+{n})，在 x={n} 两侧由负变正，所以该处为极小值点。', [-n,0,n+1])
        add('optimization', i, f'函数 $f(x)=x^3-{3*n*n}x$ 在 $[0,{2*n}]$ 上的最大值是多少？', 2*n**3,
            f'区间内驻点是 x={n}。f(0)=0，f({n})={-2*n**3}，f({2*n})={2*n**3}，比较得最大值 {2*n**3}。')
    return result
