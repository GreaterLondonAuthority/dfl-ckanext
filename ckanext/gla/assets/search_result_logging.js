function postSelectedSearchResult(data) {
    const baseURL = window.location.origin;
    const url = baseURL + '/api/action/log_chosen_search_result';
    const jsonified = JSON.stringify(data);

    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: jsonified
    }).then(function(response) {
        if (response.ok) {
            return;
        } else {
            throw new Error("Failed to log search result click");
        }
    });
}


function logResultClick(event, element, data) {
    if( data["is_search_result"] == "True") {
        event.preventDefault();
        postSelectedSearchResult(data).then(function() {
            window.location.href = element.getAttribute('href');
        });
    }

}
