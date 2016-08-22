$(function () {
    $.getJSON('/logs/pow_days.json', function (data) {
        Highcharts.setOptions({
            global : {
                timezoneOffset: -540     // 時差 -9時間(-540分）
            }
        });

        // Create the chart
        $('#pow-history-container').highcharts('StockChart', {

            rangeSelector: {
                buttons: [{
                    type: 'hour',
                    count: 1,
                    text: '1h'
                }, {
                    type: 'hour',
                    count: 12,
                    text: '12h'
                }, {
                    type: 'day',
                    count: 1,
                    text: 'Day'
                }, {
                    type: 'week',
                    count: 7,
                    text: 'Week'
                }, {
                    type: 'all',
                    text: 'All'
                }],
                selected: 2
            },
            
            credits: {
			    enabled: false
		    },

            title : {
                text : null
            },

            scrollbar : {
                enabled : false
            },
            
            series : [{
                type : 'line',
                color: '#F06A40',
                name : 'Power[W]',
                data : data,
                tooltip: {
                    valueDecimals: 0
                },
            }],

            yAxis : {
                min: 0,
                max: 6000
            }
        });
    });
});
