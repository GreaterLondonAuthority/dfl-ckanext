function postSelectedSearchResult(data) {
    var baseURL = window.location.origin;
    var xhr = new XMLHttpRequest();
    xhr.open('POST', baseURL + '/api/action/log_chosen_search_result', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    var jsonified = JSON.stringify(data);
    return new Promise(function(resolve, reject) {
        xhr.onload = function() {
            if (xhr.status === 200) {
                resolve();
            } else {
                reject(xhr.status);
            }
        };

        xhr.send(jsonified);
    });
}

function logResultClick(event, element, data) {
    if (data["is_search_result"] == "True") {
        // Check if the click is intended for a new tab or window
        if (event.ctrlKey || event.shiftKey || event.metaKey || event.button === 1) {
            // Trigger async logging call whilst also allowing the
            // default event handler to trigger. We can rely on the
            // default behaviour as the page will still exist in the
            // current tab, so the promise will execute.
            postSelectedSearchResult(data);
        } else {
            // Prevent the default anchor click behavior navigating
            // away from the page before our logging call has finished
	    event.preventDefault();

            postSelectedSearchResult(data).finally(function() {
                // Navigate to the href of the anchor after our logging has occured
                window.location.href = element.getAttribute('href');
            });
        }
    }
}
