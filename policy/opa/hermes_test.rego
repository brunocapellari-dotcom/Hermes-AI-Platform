package hermes_test

import data.hermes.allow

safe_input := {
  "money": false,
  "production_admin": false,
  "risk": "low",
  "trust": "trusted",
  "requests_scope_increase": false,
}

test_safe_request_allowed if {
  allow with input as safe_input
}

test_money_request_denied if {
  not allow with input as object.union(safe_input, {"money": true})
}

test_production_admin_denied if {
  not allow with input as object.union(safe_input, {"production_admin": true})
}

test_critical_risk_denied if {
  not allow with input as object.union(safe_input, {"risk": "critical"})
}

test_untrusted_scope_expansion_denied if {
  not allow with input as object.union(
    safe_input,
    {"trust": "untrusted", "requests_scope_increase": true},
  )
}
