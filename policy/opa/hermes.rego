package hermes

default allow := false

deny contains "money" if {
  input.money == true
}

deny contains "production_admin" if {
  input.production_admin == true
}

deny contains "critical_risk" if {
  input.risk == "critical"
}

deny contains "untrusted_scope_expansion" if {
  input.trust == "untrusted"
  input.requests_scope_increase == true
}

allow if {
  count(deny) == 0
}
