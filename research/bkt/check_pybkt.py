"""Optional fixed-parameter parity; no fitting, downloads, or access to test data.

Requires pyBKT in the interpreter used to run this command. A missing dependency
fails explicitly rather than being reported as a passing library comparison.
"""
import json

from research.bkt.model import step


def check() -> dict:
    import numpy as np
    import pandas as pd
    from pyBKT.models import Model
    parameters = {"prior": .2, "learn": .1, "guess": .2, "slip": .1}
    rows = [{"user_id": student, "skill_name": "synthetic-parity", "order_id": i, "correct": y}
            for student, seq in (("a", [0, 1, 1, 0]), ("b", [1, 0, 1])) for i, y in enumerate(seq)]
    frame = pd.DataFrame(rows)
    model = Model(seed=42, num_fits=1, parallel=False)
    model.coef_ = {"synthetic-parity": {
        "prior": parameters["prior"], "learns": np.array([parameters["learn"]]),
        "guesses": np.array([parameters["guess"]]), "slips": np.array([parameters["slip"]]),
        "forgets": np.array([0.0])}}
    model.fit(data=frame, preload=True)
    predicted_frame = model.predict(data=frame).sort_values(["user_id", "order_id"])
    predictions = predicted_frame["correct_predictions"].to_numpy()
    states, expected = {}, []
    for row in frame.sort_values(["user_id", "order_id"]).to_dict("records"):
        state = states.get(row["user_id"], parameters["prior"])
        prediction, after = step(state, row["correct"], parameters)
        expected.append(prediction)
        states[row["user_id"]] = after
    error = float(np.max(np.abs(predictions - expected)))
    if error > 1e-10:
        raise AssertionError(f"pyBKT prediction discrepancy: {error}")
    return {"status": "PASS", "synthetic_observations": len(rows), "max_absolute_error": error}


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
