# RQ4: Step Error and Misconception Evaluation

- Dataset: `data/evaluation/step_errors_benchmark.json` (66 cases)
- Validator: `app.math_validator.validate` (`symbolic-bounded-2.2.0`)
- Misconception classification is scored on structural-misconception cases only; labels are broad families mapped from catalog error IDs.
- Step numbers are 1-based. Abstention is scored on out-of-scope or ambiguous cases.
- Limitation: Các chỉ số mô tả hiệu năng trên testcase được biên soạn, không phải ước lượng độ chính xác trên quần thể học sinh hay dữ liệu tự nhiên.

## Summary

| Metric | Result | Numerator / denominator |
|---|---:|---:|
| Step localization accuracy | 100.0% | 40 / 40 incorrect cases |
| Correct-solution verification | 100.0% | 20 / 20 correct cases |
| Expected status match | 100.0% | 66 / 66 cases |
| Misconception macro precision | 100.0% | 20 structural cases |
| Misconception macro recall | 100.0% | 20 structural cases |
| Misconception macro-F1 | 100.0% | 20 structural cases |
| Arithmetic-slip false-positive rate | 0.0% | 0 / 20 slips assigned a known misconception |
| Abstention rate | 100.0% | 6 / 6 out-of-scope/ambiguous cases |

## Per-family classification

| Misconception family | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `accepted_excluded_root` | 100.0% | 100.0% | 100.0% | 1 |
| `binomial_constant_sign` | 100.0% | 100.0% | 100.0% | 1 |
| `binomial_missing_cross_terms` | 100.0% | 100.0% | 100.0% | 1 |
| `difference_of_squares_confusion` | 100.0% | 100.0% | 100.0% | 1 |
| `difference_of_squares_sign` | 100.0% | 100.0% | 100.0% | 1 |
| `distribution_missing_term` | 100.0% | 100.0% | 100.0% | 2 |
| `dividing_out_possible_zero_factor` | 100.0% | 100.0% | 100.0% | 1 |
| `incomplete_common_factor` | 100.0% | 100.0% | 100.0% | 1 |
| `inverse_operation` | 100.0% | 100.0% | 100.0% | 1 |
| `like_terms_multiplied` | 100.0% | 100.0% | 100.0% | 1 |
| `lost_domain_restriction` | 100.0% | 100.0% | 100.0% | 1 |
| `missing_product_branch` | 100.0% | 100.0% | 100.0% | 1 |
| `missing_quadratic_root` | 100.0% | 100.0% | 100.0% | 1 |
| `negative_coefficient_sign` | 100.0% | 100.0% | 100.0% | 1 |
| `negative_distribution_sign` | 100.0% | 100.0% | 100.0% | 1 |
| `one_sided_equation_operation` | 100.0% | 100.0% | 100.0% | 1 |
| `quadratic_root_sign` | 100.0% | 100.0% | 100.0% | 1 |
| `square_missing_middle_term` | 100.0% | 100.0% | 100.0% | 2 |

## Confusion matrix

Rows are ground truth; columns are predicted family. `unknown` means the validator did not return a catalog family.

| Ground truth \ Prediction | `accepted_excluded_root` | `binomial_constant_sign` | `binomial_missing_cross_terms` | `difference_of_squares_confusion` | `difference_of_squares_sign` | `distribution_missing_term` | `dividing_out_possible_zero_factor` | `incomplete_common_factor` | `inverse_operation` | `like_terms_multiplied` | `lost_domain_restriction` | `missing_product_branch` | `missing_quadratic_root` | `negative_coefficient_sign` | `negative_distribution_sign` | `one_sided_equation_operation` | `quadratic_root_sign` | `square_missing_middle_term` | `unknown` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `accepted_excluded_root` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `binomial_constant_sign` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `binomial_missing_cross_terms` | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `difference_of_squares_confusion` | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `difference_of_squares_sign` | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `distribution_missing_term` | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `dividing_out_possible_zero_factor` | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `incomplete_common_factor` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `inverse_operation` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `like_terms_multiplied` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `lost_domain_restriction` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `missing_product_branch` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `missing_quadratic_root` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| `negative_coefficient_sign` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| `negative_distribution_sign` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| `one_sided_equation_operation` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| `quadratic_root_sign` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| `square_missing_middle_term` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| `unknown` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Dataset composition

| Category | Cases |
|---|---:|
| `correct` | 20 |
| `misconception` | 20 |
| `out_of_scope` | 6 |
| `slip` | 20 |
