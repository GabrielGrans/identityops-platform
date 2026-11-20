// ServiceNow Scripted REST resource: GET /ritm/{sys_id}.
(function process(request, response) {
    function reject(status) {
        response.setStatus(status);
        response.setBody({ error: "Approval evidence is unavailable" });
    }
    if (!gs.hasRole("x_identityops.approval_reader")) {
        reject(403);
        return;
    }

    var sysId = String(request.pathParams.sys_id || "");
    var catalogItem = gs.getProperty("x_identityops.catalog_item_sys_id", "");
    var tenant = gs.getProperty("x_identityops.entra_tenant_id", "");
    if (!/^[a-f0-9]{32}$/.test(sysId) || !/^[a-f0-9]{32}$/.test(catalogItem) || !tenant) {
        reject(404);
        return;
    }

    var item = new GlideRecord("sc_req_item");
    if (!item.get(sysId) || item.getValue("cat_item") !== catalogItem || item.getValue("approval") !== "approved") {
        reject(404);
        return;
    }
    var parent = item.request.getRefRecord();
    var requester = parent.isValidRecord() ? parent.getValue("opened_by") : "";
    var beneficiary = String(item.variables.beneficiary || "");
    if (!requester || !/^[a-f0-9]{32}$/.test(beneficiary)) {
        reject(409);
        return;
    }

    var approval = new GlideRecord("sysapproval_approver");
    approval.addQuery("sysapproval", sysId);
    approval.addQuery("state", "approved");
    approval.addNotNullQuery("approver");
    approval.addQuery("approver", "!=", requester);
    approval.addQuery("approver", "!=", beneficiary);
    approval.orderBy("sys_created_on");
    approval.orderBy("sys_id");
    approval.setLimit(1);
    approval.query();
    if (!approval.next()) {
        reject(409);
        return;
    }

    // This field is maintained by the tenant administrator on sys_user.
    var person = new GlideRecord("sys_user");
    if (!person.get(beneficiary)) {
        reject(409);
        return;
    }
    response.setStatus(200);
    response.setBody({
        result: {
            sys_id: sysId,
            ritm: item.getValue("number"),
            tenant_id: tenant,
            requester_id: requester,
            beneficiary_id: beneficiary,
            approver_id: approval.getValue("approver"),
            approval_id: approval.getUniqueValue(),
            approval_state: item.getValue("approval"),
            user_object_id: person.getValue("u_identityops_entra_object_id"),
            group_object_id: String(item.variables.group_object_id || ""),
            operation: String(item.variables.operation || ""),
            justification: String(item.variables.justification || "")
        }
    });
})(request, response);
