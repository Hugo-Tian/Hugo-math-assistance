import math
import re
from collections import Counter
from backend.question_bank import items, KNOWLEDGE
from backend.schemas import QuestionInput

def test_all_demo_questions_numerically_verified():
    bank=items()
    assert len(bank)==140 and len({q['stem'] for q in bank})==140
    counts=Counter(q['knowledge_id'] for q in bank)
    assert len(counts)==14 and min(counts.values())>=5
    for q in bank:
        QuestionInput(**q)
        chosen=int(q['options'][q['answer']]);kid=q['knowledge_id'];s=q['stem']
        numbers=[int(x) for x in re.findall(r'\d+',s)]
        # Derive the answer from the actual question text, not its explanation/answer generator.
        if kid=='sets':
            end=numbers[2];start=numbers[3];bend=numbers[-1]
            expected=len(set(range(1,end+1)) & set(range(start,bend+1)))
        elif kid=='domain':expected=numbers[0]
        elif kid=='evaluation':
            coefficient=numbers[1];x=numbers[2];expected=x*x+coefficient*x
        elif kid=='monotonicity':
            a=numbers[0];valid=[int(o) for o in q['options'] if a-int(o)>0];assert valid==[chosen];expected=chosen
        elif kid=='parity':
            n=numbers[-1];valid=[int(a) for a in q['options'] if all(abs((x**3+int(a)*x*x+n*x)+((-x)**3+int(a)*x*x-n*x))<1e-9 for x in [-2,-1,1,2])];assert valid==[chosen];expected=chosen
        elif kid=='quadratic':
            coefficient=numbers[1];constant=numbers[2];expected=constant-coefficient**2/4
        elif kid=='exponential':expected=math.log(numbers[1],numbers[0])
        elif kid=='logarithm':expected=math.log(numbers[1],numbers[0])
        elif kid=='derivative_definition':
            x=numbers[2];h=1e-4;expected=((x+h)**2-(x-h)**2)/(2*h)
        elif kid=='derivative_rules':
            n=numbers[1];x=1;h=1e-4;f=lambda v:v**3+n*v*v;expected=(f(x+h)-f(x-h))/(2*h)
        elif kid=='tangent':
            x=numbers[1];y=numbers[2];h=1e-4;slope=((x+h)**2-(x-h)**2)/(2*h);expected=y-slope*x
        elif kid=='derivative_monotonicity':expected=numbers[1]/2
        elif kid=='extrema':
            coefficient=numbers[1];expected=math.sqrt(coefficient/3)
            assert 6*expected>0
        elif kid=='optimization':
            coefficient=numbers[1];end=numbers[-1];f=lambda v:v**3-coefficient*v
            expected=max(f(end*j/10000) for j in range(10001))
        assert math.isclose(chosen,expected,abs_tol=1e-5), (kid,s,chosen,expected)
        assert str(chosen) in q['explanation'] or kid=='monotonicity'
