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
                    count: 1,
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
                type : 'area',
                name : 'Power[W]',
                data : data,
                color: Highcharts.getOptions().colors[0],
                tooltip: {
                    valueDecimals: 0
                },
                
                fillColor : {
                    linearGradient : {
                        x1: 0,
                        y1: 0,
                        x2: 0,
                        y2: 1
                    },
                    stops : [
                        [0, Highcharts.getOptions().colors[0]],
                        [1, Highcharts.Color(Highcharts.getOptions().colors[0]).setOpacity(0).get('rgba')]
                    ]
                }
            }],

            yAxis : {
                min: 0,
                max: 6000
            }
        });
    });
});
