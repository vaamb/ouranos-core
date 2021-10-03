/* Graph variables and functions */
graphs = {
  options: {
    maxValues: parameters.getOptions("max_values"),
    colors: parameters.getOptions("colors"),

    chartData: {
      datasets: [{
        backgroundColor: "rgba(255,255,255,0)",
        radius: 0,
        hitRadius: 4,
        borderWidth: 2,
        type: "line",
      }]
    },

    chartLayout: {
      layout: {
        padding: {
          bottom: -2,
        }
      },
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
            mirror: true,
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
    },
  },

  store: {},

  create: function(data, separateMeasures=true) {
    // Data format: [{
    //   "baseID": "sensor_UID_or_measure",
    //   "x": [1,2,3],
    //   "y":[{"name": "name1", "values": [4, 5, 6], "measure": "measure1"},
    //        {"name": "name2", "values": [7, 8, 9], "measure": "measure1"},
    //        ],
    // }]
    function fillDataLayout(chartData, chartLayout, YsList, valuesContainer, YIndex) {
      const Y = valuesContainer["name"];
      const measureName = valuesContainer["measure"];
      YsList.push(measureName);
      chartData["datasets"][YIndex]["label"] = capitalize(Y);
      chartData["datasets"][YIndex]["data"] = valuesContainer["values"];
      // chartData["datasets"][YIndex]["yAxisID"] = 'y-' + YIndex;
      try {
        chartData["datasets"][YIndex]["borderColor"] = parameters.getOptions("colors")[measureName];
      } catch (error) {
        chartData["datasets"][YIndex]["borderColor"] = "#f0341f";
      }
      let maxValue = undefined;
      let interval = undefined;
      try {
        maxValue = parameters.getOptions("max_values")[measureName];
        interval = maxValue/10;
      } catch (error) {}
      chartLayout["scales"]["yAxes"][YIndex]["ticks"]["suggestedMax"] = maxValue;
      chartLayout["scales"]["yAxes"][YIndex]["ticks"]["steps"] = interval;
      // chartLayout["scales"]["yAxes"][YIndex]["yAxisID"] = 'y-' + YIndex;
      return [chartData, chartLayout, YsList];
    }
    function generateGraph(chartData, chartLayout, baseID, YsList) {
      let ID = baseID + "-" + YsList.join("-")
      const ctx = document.getElementById("chartCanvas-" + ID);
      let graph = new Chart(ctx, {
        type: "line",
        data: chartData,
        options: chartLayout,
      });
      Object.assign(that.store,{[ID]: {"graph": graph, "lastUpdate": new Date()}});
    }
    let that = this;
    for (const elem of data) {
      const baseID = elem["baseID"];
      const x = elem["x"];
      if (separateMeasures === true) {
        for (const y of elem["y"]) {
          let Ys = [];
          let chartData = JSON.parse(JSON.stringify(this.options.chartData));
          let chartLayout = JSON.parse(JSON.stringify(this.options.chartLayout));
          chartData["labels"] = x;
          [chartData, chartLayout, Ys] = fillDataLayout(chartData, chartLayout, Ys, y, 0);
          generateGraph(chartData, chartLayout, baseID, Ys);
        }
      } else {
        let Ys = [];
        let chartData = JSON.parse(JSON.stringify(this.options.chartData));
        let chartLayout = JSON.parse(JSON.stringify(this.options.chartLayout));
        chartData["labels"] = x;
        for (const index in elem["y"]) {
          [chartData, chartLayout, Ys] = fillDataLayout(chartData, chartLayout, Ys, elem["y"][index], index);
        }
        generateGraph(chartData, chartLayout, baseID, Ys);
      }
    }
  },

  update: function(data, separateMeasures=true, dataLimit=null) {
    // Data format: [{
    //   "baseID": "sensor_UID_or_measure",
    //   "x": 4,
    //   "y":[{"name": "name1", "values": 7, "measure": "measure1"},
    //        {"name": "name2", "values": 10, "measure": "measure1"},
    //        ],
    // }]
    for (const elem of data) {
      const baseID = elem["baseID"];
      const x = elem["x"];
      if (separateMeasures === true) {
        for (const y of elem["y"]) {
          const ID = baseID + "-" + y.name;
          try {
            let graph = this.store[ID].graph;
            graph.data.labels.push(x);
            graph.data.datasets[0].data.push(y.values);
            graph = this.sliceGraph(graph, dataLimit);
            graph.update();
          } catch(e) {
            // data from a sensor on another level
          }
        }
      } else {
        // TODO
      }
    }
  },

  sliceGraph: function(graph, dataLimit) {
    if (dataLimit) {
      let sliceLimit = dataLimit;
      if (dataLimit instanceof Date) {
        sliceLimit = graph.data.labels.filter(x => x > dataLimit).length;
      }
      graph.data.labels = graph.data.labels.slice(- sliceLimit);
      for (const dataset of graph.data.datasets) {
        dataset.data = dataset.data.slice(- sliceLimit);
      }
    }
    return graph;
  },

  formatSingleSensorHistoricData: function(singleSensorHistoricData) {
    const sensorUID = singleSensorHistoricData["sensor_uid"];
    const measure = singleSensorHistoricData["measure"];
    let x = [];
    let y = [];
    for (const value of singleSensorHistoricData["values"]) {
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
    return [{
      "baseID": sensorUID, "x": x, "y": [{"name": measure, "values": y, "measure": measure}]
    }]
  },

  formatSensorsCurrentData: function(sensorsCurrentData) {
    let rv = []
    for (const ecosystem of sensorsCurrentData) {
      let dt = new Date(ecosystem["datetime"]);
      for (const sensor of ecosystem["data"]) {
        const sensorUID = sensor["sensor_uid"];
        let y = [];
        for (const measure of sensor["measures"]) {
          const measureName = measure["name"];
          const values = measure["values"];
          y.push({"name": measureName, "values": values, "measure": measureName});
        }
        rv.push({"baseID": sensorUID, "x": dt, "y": y})  
      }
    }
    return rv;
  },

 formatSystemHistoricData: function(historicSystemData) {
   const dataOrder = historicSystemData["order"];
   const data = historicSystemData["data"];
     let x = [];
     let CPU_used = [];
     let CPU_temp = [];
     let RAM_used = [];
     let DISK_used = [];
   for (const elem of data) {
     if (Array.isArray(elem)) {
       x.push(new Date(elem[dataOrder.indexOf("datetime")]));
       CPU_used.push(elem[dataOrder.indexOf("CPU_used")]);
       CPU_temp.push(elem[dataOrder.indexOf("CPU_temp")]);
       RAM_used.push(elem[dataOrder.indexOf("RAM_used")]);
       DISK_used.push(elem[dataOrder.indexOf("DISK_used")]);
     } else if (typeof elem === "object" && elem !== null) {
       x.push(new Date(elem["datetime"]));
       CPU_used.push(elem["CPU_used"]);
       CPU_temp.push(elem["CPU_temp"]);
       RAM_used.push(elem["RAM_used"]);
       DISK_used.push(elem["DISK_used"]);
     } else {
       console.log("Unexpected data format in historic systemData");
     }
   }
   let rv = [{
     "baseID": "server", "x": x, "y": [
       {"name": "CPU used", "values": CPU_used, "measure": "CPU_used"},
       {"name": "RAM used", "values": RAM_used, "measure": "RAM_used"},
       {"name": "DISK used", "values": DISK_used, "measure": "DISK_used"},
     ]
   }]
   if (Math.max(...CPU_temp) > 0) {
     rv[0]["y"].push({"name": "CPU temp", "values": CPU_temp, "measure": "CPU_temp"})
   }
   return rv
 },

  formatSystemCurrentData: function(currentSystemData) {
    let rv = [{
     "baseID": "server", "x": currentSystemData["datetime"], "y": [
       {"name": "CPU used", "values": currentSystemData["CPU_used"], "measure": "CPU_used"},
       {"name": "RAM used", "values": currentSystemData["RAM_used"], "measure": "RAM_used"},
       {"name": "DISK used", "values": currentSystemData["DISK_used"], "measure": "DISK_used"},
     ]
    }]
    if (currentSystemData["CPU_temp"] !== null) {
      rv[0]["y"].push({"name": "CPU temp", "values": currentSystemData["CPU_temp"], "measure": "CPU_temp"})
    }
    return rv;
  },

  cleanOld: function(dataLimit = new Date() - (7 * 24 * 60 * 60 * 1000)) {
    for (const ID of Object.keys(this.store)) {
      let graph = this.store[ID].graph;
      this.sliceGraph(graph, dataLimit);
      graph.update()
    }
  },

  autoCleanOld: function (dataLimit = new Date() - (7 * 24 * 60 * 60 * 1000)) {
    setInterval(this.cleanOld(dataLimit), 1000 * 60);
  },

}


/* Gauge variables and functions */
gauges = {
  parameters: {
    defaultOpts: {
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
    },
  },
  store: {},

  createUpdateContainer: function(ID, newValue, unit="", maxValue=50) {
    let parent = $("#boardRow-" + ID);
    if (parent.length > 0) {  // Required when using fromCurrentSensorsData
      let gaugeContainer = document.getElementById("gaugeContainer-" + ID);
      if (gaugeContainer !== null) {
        if (newValue !== null) {
          // update gauge and span data
          this.store[ID].gauge.set(newValue);
          $("#gaugeValue-" + ID).text(newValue);
        } else {
          // delete gauge container
          gaugeContainer.parentNode.removeChild(gaugeContainer);
        }

      } else {
        if (newValue !== null) {
          // create new gauge container
          let container = $("<div/>").addClass("boardColumnContainer gaugeContainer max250OnScreen").attr("id", "gaugeContainer-" + ID).append(
            $("<div/>").addClass("gaugeWrapper").append(
              $("<canvas/>").attr("id", "gaugeCanvas-" + ID)
            ),
            $("<div/>").append(
              $("<span/>").attr("id", "gaugeValue-" + ID).text(newValue),
              $("<span/>").text(unit),
            ),
            );
          parent.prepend(container);

          // create the gauge object
          const target = document.getElementById("gaugeCanvas-" + ID);
          let gauge = new Gauge(target).setOptions(this.parameters.defaultOpts);
          gauge.setMinValue(0);
          gauge.maxValue = maxValue;
          gauge.animationSpeed = 32;
          gauge.set(newValue);
          Object.assign(this.store,{[ID]: {"gauge": gauge, "lastUpdate": new Date()}});
        }
      }
    }
  },

  fromCurrentSensorsData: function(currentSensorsData) {
    const units = parameters.getOptions("units");
    const maxValues = parameters.getOptions("max_values");
    for (const ecosystem of currentSensorsData) {
      for (const sensor of ecosystem["data"]) {
        const sensorUID = sensor["sensor_uid"]
        for (const measure of sensor["measures"]) {
          const measureName = measure["name"];
          const ID = sensorUID + "-" + measureName;
          const value = measure["values"];
          const unit = units[measureName];
          const maxValue = maxValues[measureName];
          gauges.createUpdateContainer(ID, value, unit, maxValue);
        }
      }
    }
  },

  fromCurrentSystemData: function(currentSystemData) {
    let measures = Object.keys(parameters.graphs.server.measures);
    const units = parameters.getOptions("units", "server");
    const maxValues = parameters.getOptions("max_values", "server");

    for (const measure of measures) {
      const value = currentSystemData[measure];
      const ID = measure;  // TODO later: add a server ID
      const unit = units[measure];
      const maxValue = maxValues[measure];
      gauges.createUpdateContainer(ID, value, unit, maxValue);
    }
  },

  cleanOld: function(maxTime=90) {
    const now = new Date();
    for (const ID of Object.keys(this.store)) {
      if (this.store[ID].lastUpdate < now - maxTime * 1000) {
        this.createUpdateContainer(ID, null)
      }
    }
  },

  autoCleanOld: function (maxTime=90) {
    setInterval(this.cleanOld(maxTime), 1000 * 60);
  },

}
