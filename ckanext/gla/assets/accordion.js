"use strict";

ckan.module('gla_accordion', function ($) {
    return {
        initialize: function () {
            $.proxyAll(this, /_on/);
            $(this.el[0]).click(function () {
                this.classList.toggle('active');
            })
        }
    };
});