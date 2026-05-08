// ✅ 正しい RegTech Compliance Protocol 実装
// std/compliance.mm の検証済み atom を import して利用する。

import "std/compliance" as compliance;

atom demo_classify_all_customer_types(customer_type: i64)
    requires: customer_type >= 0 && customer_type <= 3;
    ensures: result >= 0 && result <= 3;
    body: {
        compliance::classify_risk(customer_type)
    }

atom demo_get_transaction_limit(risk_level: i64)
    requires: risk_level >= 0 && risk_level <= 3;
    ensures: result > 0;
    body: {
        compliance::get_transaction_limit(risk_level)
    }

atom demo_check_transaction(customer_type: i64, amount: i64)
    requires: customer_type >= 0 && customer_type <= 3 && amount >= 0;
    ensures: result >= 0 && result <= 1;
    body: {
        compliance::check_transaction(customer_type, amount)
    }

atom demo_verify_all_transactions_compliant(n: i64, limit: i64)
    requires: n >= 0 && limit > 0 && forall(i, 0, n, arr[i] >= 0 && arr[i] <= limit);
    ensures: result == 1;
    body: {
        compliance::verify_all_transactions_compliant(n, limit)
    }

atom demo_approval_level(amount: i64)
    requires: amount >= 0;
    ensures: result >= 0 && result <= 3;
    body: {
        compliance::approval_level(amount)
    }
