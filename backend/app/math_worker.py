import json
import sys
from app.math_validator import validate

if __name__ == '__main__':
    data = json.load(sys.stdin)
    print(json.dumps(validate(data['problem'],data['steps']), ensure_ascii=True))
