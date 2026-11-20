// Flow Designer Script step. REST Message credentials are configured in the instance.
(function execute(inputs, outputs) {
    var sysId = String(inputs.sys_id || "");
    if (!/^[a-f0-9]{32}$/.test(sysId)) {
        throw new Error("Invalid RITM reference");
    }
    var submit = inputs.submit === true || inputs.submit === "true";
    var message = new sn_ws.RESTMessageV2("IdentityOps IAM", submit ? "submit" : "status");
    message.setHttpTimeout(12000);
    message.setRequestHeader("Accept", "application/json");
    if (submit) {
        message.setRequestHeader("Content-Type", "application/json");
        message.setRequestBody(JSON.stringify({ sys_id: sysId }));
    } else {
        message.setStringParameterNoEscape("sys_id", sysId);
    }
    var response = message.execute();
    var code = response.getStatusCode();
    outputs.http_status = code;
    outputs.retryable = code === 0 || code === 429 || code >= 500;
    if (code !== 200 && code !== 201) {
        outputs.identityops_status = outputs.retryable ? "retry" : "rejected";
        return;
    }
    var body = JSON.parse(response.getBody());
    if (body.sys_id !== sysId || typeof body.status !== "string") {
        throw new Error("Invalid IdentityOps status response");
    }
    outputs.identityops_status = body.status;
    outputs.identityops_reference = body.change_id ? String(body.change_id) : body.sys_id;
    outputs.identityops_error_code = body.error_code || "";
    outputs.simulated = body.simulated === true;
})(inputs, outputs);
