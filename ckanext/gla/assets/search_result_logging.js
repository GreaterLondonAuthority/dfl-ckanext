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
        postSelectedSearchResult(data).then(function () {
            window.location.href = element.getAttribute('href');
        });
    }

}
