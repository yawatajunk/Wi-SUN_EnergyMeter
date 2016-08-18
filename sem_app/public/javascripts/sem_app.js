//
// sem_app.js
// 
// Copyright (C) 2016 pi@blue-black.ink
//


//
// Websocket
//
const href = window.location.href ;

var pow_int;
var rcd_time;

var socketio = io.connect(href);
socketio.on("inst-power", function (data) {
    var d = JSON.parse(data);

	rcd_time = Number(d.time);
	pow_int = Number(d.power);

	if (pow_int < 2000) {
		$(function () {
			$("#progress-bar").toggleClass('progress-bar-success', true);
			$("#progress-bar").toggleClass('progress-bar-warning', false);
			$("#progress-bar").toggleClass('progress-bar-danger', false);
			$("#inst-power").css('color', 'green');
		});
	}
	else if (pow_int < 4000) {
		$(function () {
			$("#progress-bar").toggleClass('progress-bar-success', false);
			$("#progress-bar").toggleClass('progress-bar-warning', true);
			$("#progress-bar").toggleClass('progress-bar-danger', false);
			$("#inst-power").css('color', 'orange');
		});
	}
	else {
		$(function () {
			$("#progress-bar").toggleClass('progress-bar-success', false);
			$("#progress-bar").toggleClass('progress-bar-warning', false);
			$("#progress-bar").toggleClass('progress-bar-danger', true);
			$("#inst-power").css('color', 'red');
		});
	}

	$(function () {
		$("#inst-power").text(String(pow_int) + ' W');
	});
	
	var gain_int = Math.round(pow_int / 6000.0 * 100.0);	// 6000 W -> 100 %
	if (gain_int > 100.0) {
		gina_int = 100;
	} 
	var gain_str = String(gain_int) + '%';
	$(function () {
		$("#progress-bar").css('width', gain_str);
	});
});	// end of socket.on()


//
// highcharts: power useage
//
$(function () {

	$('#chart-container').highcharts({
		chart: {
			type: 'gauge',
			plotBackgroundColor: null,
			plotBackgroundImage: null,
			plotBorderWidth: 0,
			plotShadow: false,

			events : {
				load: function () {
					var point = this.series[0].points[0]
					setInterval(function () {
						point.update(pow_int);
					}, 1000);
				}
			}
		},
		
		credits: {
			enabled: false
		},
			
		title: {
			text: 'Power Usage'
		},

		pane: {
			startAngle: -150,
			endAngle: 150,
			background: [{
				backgroundColor: {
					linearGradient: { x1: 0, y1: 0, x2: 0, y2: 1 },
					stops: [
						[0, '#FFF'],
						[1, '#333']
					]
				},
				borderWidth: 0,
				outerRadius: '100%'
			}, {
				backgroundColor: {
					linearGradient: { x1: 0, y1: 0, x2: 0, y2: 1 },
					stops: [
						[0, '#333'],
						[1, '#FFF']
					]
				},
				borderWidth: 0,
				outerRadius: '100%'
			}, {
				// default background
			}, {
				backgroundColor: '#DDD',
				borderWidth: 0,
				outerRadius: '100%',
				innerRadius: '100%'
			}]
		},

		// the value axis
		yAxis: {
			min: 0,
			max: 6000,

			minorTickInterval: 'auto',
			minorTickWidth: 1,
			minorTickLength: 10,
			minorTickPosition: 'inside',
			minorTickColor: '#666',

			tickPixelInterval: 30,
			tickWidth: 2,
			tickPosition: 'inside',
			tickLength: 10,
			tickColor: '#666',
			labels: {
				step: 2,
				rotation: 'auto'
			},
			title: {
				text: 'Watt'
			},
			plotBands: [{
				from: 0,
				to: 2000,
				color: '#55BF3B' // green
			}, {
				from: 2000,
				to: 4000,
				color: '#DDDF0D' // yellow
			}, {
				from: 4000,
				to: 6000,
				color: '#DF5353' // red
			}]
		},

		series: [{
			name: 'Power',
			data: [0],
			tooltip: {
				valueSuffix: ' [W]'
			}
		}]				
	});
});
