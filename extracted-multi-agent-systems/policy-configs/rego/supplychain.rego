package supplychain

default allow = false

deny[msg] {
    not input.image
    msg := "image reference missing"
}

deny[msg] {
    not input.image.signed
    msg := "image not signed"
}

deny[msg] {
    not input.sbom.generated
    msg := "sbom missing"
}

deny[msg] {
    some vuln
    vuln := input.vulnerabilities[_]
    lower(vuln.severity) == "critical"
    msg := sprintf("critical vulnerability present: %s", [vuln.id])
}

deny[msg] {
    some license in input.licenses
    license.blocked
    msg := sprintf("blocked license detected: %s", [license.name])
}

allow {
    not deny[_]
}
