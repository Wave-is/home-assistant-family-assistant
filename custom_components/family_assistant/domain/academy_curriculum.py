"""Original, local practice exercises. Version 1 is immutable for saved courses."""

from fractions import Fraction
from hashlib import sha256

VERSION = 1
# id, grade, Ukrainian title, English title, Ukrainian explanation, English explanation
TOPICS = (
    ("divisibility", 6, "Подільність", "Divisibility",
     "Число ділиться на дільник, якщо остача від ділення дорівнює нулю.",
     "A number is divisible by a divisor when the remainder is zero."),
    ("fractions", 6, "Додавання дробів", "Adding fractions",
     "Зведи дроби до спільного знаменника, додай чисельники та скороти результат.",
     "Use a common denominator, add the numerators, and simplify."),
    ("ratio", 6, "Відношення і пропорції", "Ratios and proportions",
     "Знайди значення однієї частини, а потім помнож на потрібну кількість частин.",
     "Find the value of one part, then multiply by the required number of parts."),
    ("percent", 6, "Відсотки", "Percentages",
     "Один відсоток — одна сота. Помнож число на відсоток і поділи на 100.",
     "One percent is one hundredth. Multiply the number by the percentage and divide by 100."),
    ("signed", 6, "Раціональні числа", "Signed numbers",
     "Додаючи числа з різними знаками, відніми менший модуль від більшого.",
     "When adding numbers with different signs, subtract the smaller absolute value from the larger."),
    ("linear6", 6, "Рівняння", "Equations",
     "Виконай однакову обернену дію з обох боків рівняння.",
     "Apply the same inverse operation to both sides of the equation."),
    ("powers", 7, "Степені", "Powers",
     "Степінь показує, скільки разів основа множиться сама на себе.",
     "An exponent tells how many times the base is multiplied by itself."),
    ("expressions", 7, "Одночлени та многочлени", "Monomials and polynomials",
     "Подібні доданки мають однакову буквену частину; додавай їхні коефіцієнти.",
     "Like terms have the same variable part; add their coefficients."),
    ("linear7", 7, "Лінійні рівняння", "Linear equations",
     "Перенеси вільний доданок і поділи обидві частини на коефіцієнт при x.",
     "Move the constant and divide both sides by the coefficient of x."),
    ("functions", 7, "Лінійна функція", "Linear functions",
     "Підстав задане значення x у формулу функції та обчисли y.",
     "Substitute the given x into the formula and calculate y."),
    ("angles", 7, "Кути трикутника", "Triangle angles",
     "Сума внутрішніх кутів трикутника дорівнює 180 градусів.",
     "The interior angles of a triangle sum to 180 degrees."),
    ("system", 7, "Системи рівнянь", "Systems of equations",
     "Додай два рівняння, щоб усунути y, потім поділи обидві частини на 2.",
     "Add the two equations to eliminate y, then divide both sides by two."),
)
BY_ID = {row[0]: row for row in TOPICS}


def catalog(language):
    uk = language == "uk"
    return [
        {"id": key, "grade": grade, "title": ua if uk else en,
         "lesson": explanation_ua if uk else explanation_en}
        for key, grade, ua, en, explanation_ua, explanation_en in TOPICS
    ]


def question(topic, assignment, sequence, language):
    """Regenerate the same task without storing or returning its answer to clients."""
    digest = sha256(f"{VERSION}:{assignment}:{topic}:{sequence}".encode()).digest()
    a, b, c = (2 + n % 8 for n in digest[:3])
    uk = language == "uk"
    if topic == "divisibility":
        n, d = a * b + c, b
        prompt = f"{n} ÷ {d}: " + ("остача?" if uk else "remainder?")
        answer = n % d
    elif topic == "fractions":
        prompt, answer = f"{a}/{b} + {c}/{a}", Fraction(a, b) + Fraction(c, a)
    elif topic == "ratio":
        prompt = f"{a}:{b}, " + (f"перша частина = {a*c}. Друга?" if uk else
                                  f"first share = {a*c}. Second share?")
        answer = b * c
    elif topic == "percent":
        prompt, answer = f"{a*5}% × {b*20}", a * b
    elif topic == "signed":
        prompt, answer = f"−{a*3} + {b*2}", -a * 3 + b * 2
    elif topic in {"linear6", "linear7"}:
        k = 1 if topic == "linear6" else a
        prompt, answer = f"{k}x + {b} = {k*c+b}", c
    elif topic == "powers":
        exponent = 2 + c % 2
        prompt, answer = f"{a}^{exponent}", a ** exponent
    elif topic == "expressions":
        prompt = f"{a}x + {b}x: " + ("коефіцієнт при x?" if uk else "coefficient of x?")
        answer = a + b
    elif topic == "functions":
        prompt, answer = f"y = {a}x + {b}; x = {c}; y = ?", a*c+b
    elif topic == "angles":
        prompt, answer = f"α = {a*8}°, β = {b*7}°, γ = ?", 180-a*8-b*7
    elif topic == "system":
        prompt, answer = f"x + y = {a+b}; x − y = {a-b}; x = ?", a
    else:
        raise ValueError("unknown topic")
    return prompt, Fraction(answer)
