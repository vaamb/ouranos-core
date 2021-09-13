/* Graph variables and functions */

window["graphs"] = {parameters: {}}
window["gauges"] = {}

const defaultChartData = {
  datasets: [{
    backgroundColor: "rgba(255,255,255,0)",
    radius: 0,
    hitRadius: 4,
    borderWidth: 2,
    type: "line",
  }]
};

const defaultChartLayout = {
  scales: {
    xAxes: [{
      type: "time",
      barPercentage: 1.27,
      time: {
        unit: "day",
        unitStepSize: 1,
        displayFormats: {"day": "ddd DD"},
        tooltipFormat: 'YYYY-MM-DD HH:mm',
      },
      ticks: {
        maxRotation: 90,
        minRotation: 65,
      },
    }],
    yAxes: [{
      display: true,
      ticks: {
        beginAtZero: true,
      }
    }]
  },
  legend: {
    display: false
  },
  maintainAspectRatio: false,
  responsive: true,
};

function formatHistoricSensorsData(historicSensorsData) {
  const sensorUID = historicSensorsData["sensor_uid"];
  const measure = historicSensorsData["measure"];
  let x = [];
  let y = [];
  for (const value of historicSensorsData["values"]) {
    if (Array.isArray(value)) {
      x.push(new Date(value[0]));
      y.push(Number(value[1]).toFixed(1));
    } else if (typeof value === "object" && value !== null) {
      x.push(new Date(value["datetime"]));
      y.push(Number(value["value"]).toFixed(1));
    } else {
      console.log("Unexpected data format in historicSensorsData - ",
      sensorUID, " - ", measure);
    }
  }
  let color = "#f0341f";
  try {
    color = window[colors][measure];
  } catch (error) {}
  let maxValue = null;
  try {
    maxValue = maxValues[measure];
  } catch (error) {}
  return [{
    "UID": sensorUID, "x": x, "y": [{[measure]: y}], "color": {[measure]: color}, "maxValue": {[measure]: maxValue}
  }]
}

function formatCurrentSensorsData(CurrentSensorsData) {
  let results = [];
  for (const sensorUID in CurrentSensorsData["data"]) {
    if (CurrentSensorsData["data"].hasOwnProperty(sensorUID)) {
      let measures = [];
        for (const measure in CurrentSensorsData["data"][sensorUID]) {
          if (CurrentSensorsData["data"][sensorUID].hasOwnProperty(measure)) {
            measures.push({[measure]: CurrentSensorsData["data"][sensorUID][measure]});
          }
        }
      results.push({
        "UID": sensorUID, "x": new Date(CurrentSensorsData["datetime"]), "y": measures
      });
    }
  }
  return results;
}

function createGraph(data, separateMeasures=true) {
  // Data format: [{
  //   "UID": "sensor_uid",
  //   "x": [1,2,3],
  //   "y":[{"measure1": [4, 5, 6]}, {"measure2": [7, 8, 9]}],
  //   "color": {"measure1": "red", "measure2": "blue"},
  //   "maxValue": {"measure1": 42},
  // }]
  function fillDataLayout(value, index, chartData, chartLayout, measures, colors, maxValues) {
    const measure = Object.keys(value)[0];
    measures.push(measure);
    chartData["datasets"][index]["label"] = capitalize(measure);
    chartData["datasets"][index]["data"] = value[measure];
    try {
      chartData["datasets"][index]["borderColor"] = colors[measure];
    } catch (error) {
      chartData["datasets"][index]["borderColor"] = "#f0341f";
    }
    let maxValue = undefined;
    let interval = undefined;
    try {
      maxValue = maxValues[measure];
      interval = maxValue/10;
    } catch (error) {}
    if (["humidity", "moisture"].includes(measure)) {
      chartLayout["scales"]["yAxes"][index]["ticks"]["max"] = maxValue;
    } else {
      chartLayout["scales"]["yAxes"][index]["ticks"]["suggestedMax"] = maxValue;
    }
    chartLayout["scales"]["yAxes"][index]["ticks"]["steps"] = interval;
    return [chartData, chartLayout, measures];
  }
  function generateGraph(sensorUID, measures, chartData, chartLayout) {
    const ctx = document.getElementById("chartCanvas-" + sensorUID + "-" + measures.join("-"));
    let chart = new Chart(ctx, {
      type: "line",
      data: chartData,
      options: chartLayout,
    });
    Object.assign(window["graphs"], {[sensorUID + "_" + measures.join("_")]:  chart});
  }

  for (const sensor of data) {
    const sensorUID = sensor["UID"];
    const x = sensor["x"];
    if (separateMeasures === true) {
      for (const yData of sensor["y"]) {
        let measures = [];
        let chartData = JSON.parse(JSON.stringify(defaultChartData));
        let chartLayout = JSON.parse(JSON.stringify(defaultChartLayout));
        chartData["labels"] = x;
        [chartData, chartLayout, measures] = fillDataLayout(yData, 0, chartData, chartLayout, measures, sensor["color"], sensor["maxValue"]);
        generateGraph(sensorUID, measures, chartData, chartLayout);
      }
    } else {
      let measures = [];
      let chartData = JSON.parse(JSON.stringify(defaultChartData));
      let chartLayout = JSON.parse(JSON.stringify(defaultChartLayout));
      chartData["labels"] = x;
      for (const index of sensor["y"]) {
        [chartData, chartLayout, measures] = fillDataLayout(sensor["y"][index], index, chartData, chartLayout, measures, sensor["color"], sensor["maxValue"]);
      }
    }
  }
}

function updateGraphs2(data, separateMeasures=true, dataLimit=null) {
  // Data format: [{
  //   "UID": "sensor_uid",
  //   "x": [1,2,3], 
  //   "y":[{"measure1": 7}, {"measure2": 10}], 
  // }]
  function getMeasures(yData, measures, ) {
    const measure = Object.keys(yData)[0];
    const value = yData[measure];
    Object.assign(measures, {[measure]: value});
    return measures;
  }
  function cutLimit(data, dataLimit) {
    if (dataLimit) {
      if (dataLimit instanceof Date) {
        dataLimit = data.filter(x => x > dataLimit).length;
      }
      return data.slice(- dataLimit);
    } else {
      return data;
    }
  }
  function updateGraph(sensorUID, x, measures) {
    let chart = window["graphs"][sensorUID + "_" + Object.keys(measures).join("_")];
    chart.data.labels.push(x);
    chart.data.labels = cutLimit(chart.data.labels, dataLimit);
    for (const index in chart.data.datasets) {
      const measure = chart.data.datasets[index]["label"];
      data = chart.data.datasets[index]["data"];
      data.push(measures[measure]);
      data = cutLimit(data, dataLimit);
      chart.data.datasets[index]["data"] = data;
    }
  }

  for (const sensor of data) {
    const sensorUID = sensor["UID"];
    const x = sensor["x"];
    if (separateMeasures === true) {
      for (const yData of sensor["y"]) {
        let measures = {};
        measures = getMeasures(yData, measures);
        try {
          updateGraph(sensorUID, x, measures);
        } catch(error) {
          console.log(error)
        }
      }
    } else {
      let measures = {};
      for (const yData of sensor["y"]) {
        getMeasures(yData, measures);
      }
      try {
        updateGraph(sensorUID, x, measures);
      } catch(error) {
        console.log(error);
      }
    }
  }
}

function updateGraph(ID, newLabel, newData, dataLimit=null) {
  let chart = window["graphs"][ID];
  if (newLabel !== null && newData !== null) {
    chart.data.labels.push(newLabel);
    chart.data.datasets[0]["data"].push(newData);
  }
  if (dataLimit) {
    let sliceLimit = dataLimit;
    if (dataLimit instanceof Date) {
      sliceLimit = chart["data"].labels.filter(x => x > dataLimit).length;
    }
    // TODO: check when dataLimit = null
    chart.data.labels = chart["data"].labels.slice(- sliceLimit);
    chart.data.datasets[0].data = chart["data"].datasets[0].data.slice(- sliceLimit);
  }
  chart.update()
}

/* Gauge variables and functions */
const defaultGaugeOpts = {
  lines: 12,
  angle: -0.11,            // The span of the gauge arc
  lineWidth: 0.25,         // The line thickness
  radiusScale: 0.7,        // Relative radius
  pointer: {
    length: 0.6,           // Relative to gauge radius
    strokeWidth: 0.035,    // The thickness
    color: "#000000"       // Fill color
  },
  limitMax: true,          // If false, max value increases automatically if value > maxValue
  limitMin: true,          // If true, the min value of the gauge will be fixed
  colorStart: "#6FADCF",   // Colors
  colorStop: "#8FC0DA",    // just experiment with them
  strokeColor: "#E0E0E0",  // to see which ones work best for you
  generateGradient: true,
  highDpiSupport: true,    // High resolution support
};

function updateGaugeContainer(ID, newValue, unit="", maxValue=50) {
  let gaugeContainer = document.getElementById("gaugeContainer_" + ID);
  if (gaugeContainer !== null) {
    if (newValue !== null) {
      // update gauge and span data
      let gauge = window["gauges"][ID];
      gauge.set(newValue);
      $("#gaugeValue_" + ID).text(newValue);
    } else {
      // delete gauge container
      gaugeContainer.parentNode.removeChild(gaugeContainer);
    }

  } else {
    if (newValue !== null) {
      // create new gauge container
      gaugeContainer = document.createElement("div");
      gaugeContainer.className = "boardColumnContainer gaugeContainer max250OnScreen";
      gaugeContainer.setAttribute("id", "gaugeContainer_" + ID);
      // create gauge wrapper
      let gaugeWrapper = document.createElement("div");
      gaugeWrapper.className = "gaugeWrapper";
      let gaugeCanvas = document.createElement("canvas");
      gaugeCanvas.setAttribute("id", "gaugeCanvas_" + ID);
      gaugeWrapper.appendChild(gaugeCanvas);
      gaugeContainer.appendChild(gaugeWrapper);
      // create gauge data span
      let dataDiv = document.createElement("div");
      let dataSpan = document.createElement("span");
      dataSpan.setAttribute("id", "gaugeValue_" + ID);
      dataSpan.appendChild(
        document.createTextNode(newValue)
      );
      dataDiv.appendChild(dataSpan);
      dataDiv.appendChild(
        document.createTextNode(unit)
      );
      gaugeContainer.appendChild(dataDiv);
      let parent = document.getElementById("boardRow_" + ID);
      parent.prepend(gaugeContainer);
      // create the gauge object
      const target = document.getElementById("gaugeCanvas_" + ID);
      var gauge = new Gauge(target).setOptions(defaultGaugeOpts);
      gauge.setMinValue(0);
      gauge.maxValue = maxValue;
      gauge.animationSpeed = 32;
      gauge.set(newValue);
      Object.assign(window["gauges"],{[ID]: gauge});
    }
  }
}
