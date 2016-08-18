$(function () {
$.get('sem_log/pow_day_0.csv', function(csv) {
        $('#container').highcharts('StockChart', {


            rangeSelector : {
                selected : 1
            },

            title : {
                text : 'AAPL Stock Price'
            },

            series : [{
                name : 'power',
                data : csv,
                marker : {
                    enabled : true,
                    radius : 3
                },
                shadow : true,
                tooltip : {
                    valueDecimals : 2
                }
            }]
        });
    });
});
