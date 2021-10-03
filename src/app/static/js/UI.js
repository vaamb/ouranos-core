$(function() {
  let Accordion = function(el, multiple) {
    this.el = el || {};
    // more then one submenu open?
    this.multiple = multiple || false;

    let dropdownlink = this.el.find('.dropdownLink');
    dropdownlink.on('click',
                    { el: this.el, multiple: this.multiple },
                    this.dropdown);
  };
  Accordion.prototype.dropdown = function(e) {
    let $el = e.data.el,
        $this = $(this),
        //this is the ul.submenuItems
        $next = $this.next();

    $next.slideToggle();
    $this.parent().toggleClass('open');

    if(!e.data.multiple) {
      //show only one menu at the same time
      $el.find('.submenuItems').not($next).slideUp().parent().removeClass('open');
    }
  }
  new Accordion($('.accordionMenu'), false);
})


$(document).ready(function() {
  // Menu and user dropdown in small media
  if (window.matchMedia("(max-width: 768px)").matches) {
    $("#navTopBox").click(function () {
      $("#navToggle").toggleClass("show");
    });
    $("#userDropdown").click(function () {
      $("#userDropdownContent").toggleClass("show");
    });
  }

  // Flash messages
  function flashMsgFadeOut() {
    $(".flash-message").fadeOut().empty();
  }
  setTimeout(flashMsgFadeOut, 1500);

  // Modal
  let modalRoot = document.getElementById("modal-root");

  function closeModal() {
    $("div#modal-root").addClass("hide");
    $("div#modal-content").empty();
  }

  document.getElementById("close-modal").onclick = function() {closeModal()};

  window.onclick = function(event) {
    if(event.target === modalRoot) {
      closeModal();
    }
  }

});

// Go back
function goBack() {
  window.history.back();
}

// Home page
UI = {
  createEcosystemBoards: function(ecosystemsInfo) {
    let parentDiv = $("<div/>").attr("id", "ecosystemsOverview");
    parentDiv.append($("<h2/>").text("Ecosystems overview"));
    parentDiv.append($("<div/>").attr("id", "ecosystemsContent"));
    $("div#contentContainer").append(parentDiv);

    for (const ecosystem of ecosystemsInfo) {
      let newDiv = $("<div/>").addClass("board").css({"min-height": "150px"});
      let subtitle = $("<h1/>").css({"text-align": "center"}).html(ecosystem["name"] + "&nbsp");
      subtitle.append(
        $("<i/>").addClass("fa fa-circle statusIcon").attr("id", ecosystem["uid"] + "_status")
      )
      newDiv.append(subtitle);
      newDiv.append(
        $("<div/>").addClass("boardRowContainer").attr("id", ecosystem["uid"] + "_info").css({"background": "#ccc"})
      );
      parentDiv.append(newDiv);
    }
  },

  updateEcosystemBoardsStatus: function(ecosystemsInfo) {
    for (const ecosystem of ecosystemsInfo) {
      if (ecosystem["connected"]  ) {
        if (ecosystem["status"]) {
          $("i#" + ecosystem["uid"] + "_status").addClass("on").removeClass("deco");
        } else {
          $("i#" + ecosystem["uid"] + "_status").addClass("off").removeClass("deco");
        }
      } else {
        $("i#" + ecosystem["uid"] + "_status").addClass("deco").removeClass("on off");
        $("i#" + ecosystem["uid"] + "_light_status").addClass("deco").removeClass("on off");
      }
    }
 },

  checkManagement: function(managementObject, ecosystem_uid, management) {
    for (const ecosystem of managementObject) {
      if (ecosystem["uid"] === ecosystem_uid) {
        if (ecosystem[management]) {
          return true;
        }
      }
    }
    return false;
  },

  updateEcosystemBoardsLightBoxes: function(ecosystemsLight, ecosystemsManagement) {
    // TODO: don't touch to light status, or make statusBoard classes more important
    for (const light of ecosystemsLight) {
      if (this.checkManagement(ecosystemsManagement, light["ecosystem_uid"], "light")) {
        let newDiv = $("<div/>").addClass("boardFlexItem boardColumnContainer").attr("id", light["ecosystem_uid"] + "_light_board");
        newDiv.append(
          $("<div/>").addClass("boardSubTitle").text("Light")
        );
        let statusIcon = $("<i/>").addClass("fas fa-sync-alt").attr("id", light["ecosystem_uid"] + "_light_status");
        if (light["status"]) {statusIcon.addClass("on");} else {statusIcon.addClass("off");}
        if (light["mode"] === "automatic") {statusIcon.addClass("fa-spin");}
        newDiv.append(
          $("<div/>").addClass("boardFlexItemU").text("Status: ").append(statusIcon)
        );
        if (["elongate", "mimic"].includes(light["method"])) {
          for (const TOD of ["morning", "evening"]) {
            if (light[TOD + "_start"] && light[TOD + "_end"]) {
              const start = new Date(light[TOD + "_start"]);
              const end = new Date(light[TOD + "_end"]);
              if (start < end) {
                newDiv.append(
                  $("<div/>").addClass("boardFlexItemU").text(
                    capitalize(TOD) + " lighting from " + start.toLocaleTimeString([], {timeStyle: "short"}) +
                    " to " +   end.toLocaleTimeString([], {timeStyle: "short"})
                  )
                );
              }
            }
          }
        }
        let oldDiv = $("#" + light["ecosystem_uid"] + "_light_board");
        if (oldDiv.length) {
          oldDiv.replaceWith(newDiv);
        } else {
          let parentDiv = $("#" + light["ecosystem_uid"] + "_info");
          parentDiv.insertAt(parameters.subBoxesOrder.indexOf("light"), newDiv);
        }
      }
    }
    this.fillBoxesIfEmpty()
  },

  updateEcosystemBoardsCurrentSensorBoxes: function(currentSensorsData, ecosystemsManagement) {
    for (const ecosystem of currentSensorsData) {
      let store = {};
      for (const sensor of ecosystem["data"]) {
        for (const measure of sensor["measures"]) {
          store[measure["name"]] = store[measure["name"]] || [];
          store[measure["name"]].push(measure["values"]);
        }
      }
      for (const sensorLevel of ["environment", "plants"]) {
        const units = parameters.getOptions("units", sensorLevel);
        if (Object.keys(store).some(measure => Object.keys(units).includes(measure))) {
          let newDiv = $("<div/>").addClass("boardFlexItem boardColumnContainer").attr("id", ecosystem["ecosystem_uid"] + "_" + sensorLevel + "_sensors_box");
          newDiv.append(
            $("<div/>").addClass("boardSubTitle").text(capitalize(sensorLevel))
          );
          for (const measure in units) {
            if (store.hasOwnProperty(measure)) {
              let sum = 0;
              for (let i = 0; i < store[measure].length; i++) {
                sum += store[measure][i]
              }
              let avg = (Math.round(10 * sum / store[measure].length) / 10).toFixed(1);
              newDiv.append(
                $("<div/>").addClass("boardFlexItemU").text(
                  capitalize(measure).replace("_", " ") + ": " + avg + units[measure]
                )
              )
            }
          }
          let oldDiv = $("#" + ecosystem["ecosystem_uid"] + "_" + sensorLevel + "_sensors_box");
          if (oldDiv.length) {
            oldDiv.replaceWith(newDiv);
          } else {
            let parentDiv = $("#" + ecosystem["ecosystem_uid"] + "_info");
            parentDiv.insertAt(parameters.subBoxesOrder.indexOf("light"), newDiv);
          }
        }
      }
    }
    this.fillBoxesIfEmpty()
  },

  fillBoxesIfEmpty: function() {
    let parents = $("div[id$='_info']");
    for (const parent of parents) {
      const ecosystem_uid = parent.id.replace("_info", "");
      if (parent.children.length < 1) {
        let newDiv = $("<div/>").addClass("boardFlexItem boardColumnContainer").attr("id", ecosystem_uid + "_fill_box");
        newDiv.append(
          $("<div/>").addClass("boardSubTitle").text("TODO")
        );
        newDiv.append(
          $("<div/>").addClass("boardFlexItemU").text("Display info when nothing's available")
        );

        $("#" + ecosystem_uid + "_info").append(newDiv)
      } else if (parent.children.length > 1) {
        if ($("#" + ecosystem_uid + "_info").has("#" + ecosystem_uid + "_fill_box").length > 0) {
          $("#" + ecosystem_uid + "_fill_box").remove()
        }
      }
    }
  },

  injectHomeEcosystemBoards: function() {
    $.ajax({
      url: "/api/ecosystems/status",
      type: "get",
      data: {ecosystems: "recent"},
      success: function(response) {
        UI.createEcosystemBoards(response);
        UI.updateEcosystemBoardsStatus(response);
      }
    });

    socket.on("ecosystem_status", function(msg) {
      UI.updateEcosystemBoardsStatus(msg);
    });

    let getManagement = $.ajax({
      url: "/api/ecosystems/management",
      type: "get",
      data: {ecosystems: "recent"},
    }).promise();

    getManagement.then(function(ecosystemsManagement) {
      $.ajax({
        url: "/api/ecosystems/light",
        type: "get",
        data: {ecosystems: "recent"},
        success: function(response) {
          UI.updateEcosystemBoardsLightBoxes(response, ecosystemsManagement);
        }
      });

      socket.on("light_data", function(msg) {
        UI.updateEcosystemBoardsLightBoxes(msg, ecosystemsManagement);
      });

      $.ajax({
        url: "/api/ecosystems/sensors",
        type: "get",
        data: {ecosystems: "recent", scope: "current"},
        success: function(response) {
          UI.updateEcosystemBoardsCurrentSensorBoxes(response, ecosystemsManagement);
        }
      });

      socket.on("current_sensors_data", function(msg) {
        UI.updateEcosystemBoardsCurrentSensorBoxes(msg, ecosystemsManagement);
      });
    });
  },

  injectHomeServerBoard: function() {
    let getCurrentSystemData = $.ajax({
      url: "/api/system/current_data",
      type: "get",
    }).promise();

    getCurrentSystemData.then(function(currentSystemData) {
      function  updateServerUptime(serverStartTime, serverLastSeen) {
        let now = new Date();
        if ((now - serverLastSeen) > 15 * 1000) {
          $('#server_uptime').text("Lost connection with server");
        } else {
          let timeDelta = serverStartTime - now;
          let uptime = humanizeDuration(timeDelta, {
            largest: 2, units: ['y', 'mo', 'w', 'd', 'h', 'm', 's'], maxDecimalPoints: 0, delimiter: " and "
          });
          $('#server_uptime').text(uptime);
        }
      }

      function updateSystemDataSpans(currentSystemData) {
        systemDataCPU.push(currentSystemData["CPU_used"]);
        systemDataCPU = systemDataCPU.slice(-5);
        let systemDataCPUSum = 0;
        for (let i = 0; i < systemDataCPU.length; i++) {
          systemDataCPUSum += systemDataCPU[i];
        }
        $('#server_CPU_used').text((Math.round(10 * systemDataCPUSum /
          systemDataCPU.length) / 10 ).toFixed(2));

        for (const span of systemDataSpans) {
          $('#server_' + span).text(Number(currentSystemData[span]).toFixed(2));
        }
      }

      const systemDataSpans = ["CPU_temp", "RAM_used", "RAM_total", "DISK_used", "DISK_total"];
      let serverStartTime = new Date(currentSystemData["start_time"]);
      let serverLastSeen = new Date(currentSystemData["datetime"]);
      let systemDataCPU = [];

      updateServerUptime(serverStartTime, serverLastSeen);
      setInterval(function() {updateServerUptime(serverStartTime, serverLastSeen)}, 1000);

      updateSystemDataSpans(currentSystemData);

      socketAdmin.on('current_server_data', function(msg) {
        serverLastSeen = new Date(msg["datetime"]);
        updateSystemDataSpans(msg);
      });
    })
  },

  // Sensors Page
  createSensorBoardsFromSkeleton: function (skeleton) {
    const icons = parameters.getOptions("icons");
    parent = $("#contentContainer");
    for (const ecosystem of skeleton) {
      const sensorsLevel = ecosystem["level"]
      for (const measure of parameters["graphs"][sensorsLevel]["order"]) {
        if (ecosystem["sensors_skeleton"][measure] === undefined) {
          continue
        }
        let newDiv = $("<div/>").attr("id", measure);
        newDiv.append($("<h2/>").text(capitalize(measure.replace("_", " "))));
        for (const sensorUID of Object.keys(ecosystem["sensors_skeleton"][measure])) {
          let board = $("<div/>").addClass("board").attr("id", "board-" + measure + "-" + sensorUID);
          let title = $("<h1/>").text(ecosystem["sensors_skeleton"][measure][sensorUID]);
          title.prepend($("<i/>").addClass(icons[measure] + " leftIco"))
          board.append(title);
          board.append(
            $("<div/>").addClass("boardRowContainer").attr("id", "boardRow-" + sensorUID + "-" + measure).css({"row-gap": "6px"}).append(
              $("<div/>").addClass("chartContainer boardFlexItem").css({"height": "195px"}).append(
                $("<canvas/>").attr("id", "chartCanvas-" + sensorUID + "-" + measure)
              )
            )
          )
          newDiv.append(board);
        }
        parent.append(newDiv);
      }
    }

  },

  createSensorBoardsGraphsFromSkeleton: function(skeleton, graphUpdatePeriod) {
    const updateCoeff = 1000 * 60 * graphUpdatePeriod;
    let now = new Date();
    now = new Date(Math.floor((now.getTime() - 65 * 1000) / updateCoeff) * updateCoeff);
    for (const measure of Object.keys(skeleton[0]["sensors_skeleton"])) {
      for (const sensorUID of Object.keys(skeleton[0]["sensors_skeleton"][measure])) {
        const dataID = "sensorHistoricData_" + sensorUID + "_" + measure;
        const storedData = sessionStorage.getItem(dataID);
        let download = true;
        if (storedData !== null) {
          const parsedData = JSON.parse(storedData);
          const lastUpdate = new Date(parsedData.lastUpdate)
          if (lastUpdate.valueOf() === now.valueOf()){
            download = false;
            graphs.create(parsedData.data);
          }
        }
        if (download) {
          $.ajax({
            url: "/api/ecosystems/sensors/" + sensorUID + "/" + measure,
            type: "get",
            async: true,
            success: function(response) {
              const data = graphs.formatSingleSensorHistoricData(response);
              sessionStorage.setItem(dataID, JSON.stringify({
                "lastUpdate": now, "data": data,
              }))
              graphs.create(data);
            }
          });
        }
      }
    }
    Object.assign(graphs.store, {updateDT: new Date().setSeconds(0, 0)});
  },

  updateSensorBoardsFromSensorsCurrentData: function(skeleton, graphUpdatePeriod) {
    socket.on('current_sensors_data', function(msg) {
      let UIDs = []
      for (const ecosystem of skeleton) {
        UIDs.push(ecosystem["ecosystem_uid"])
      }
      for (const ecosystem of msg) {
        if (! UIDs.includes(ecosystem["ecosystem_uid"])) {
          continue;
        }
        const now = new Date().setSeconds(0, 0);
        const dt = new Date(ecosystem["datetime"]);
        $("#lastRecordTime").text("Last sensors measure at " + dt.toLocaleTimeString())
        gauges.fromCurrentSensorsData([ecosystem]);
        if ((dt.getMinutes() % graphUpdatePeriod === 0) && (graphs.store.updateDT !== now)) {
          let graphsInfo = graphs.formatSensorsCurrentData([ecosystem]);
          graphs.update(graphsInfo);
          Object.assign(graphs.store, {updateDT: now});
        }
      }
    });
  },

  createSensorBoardsGauges: function(skeleton) {
    let UIDs = []
    for (const ecosystem of skeleton) {
      UIDs.push(ecosystem["ecosystem_uid"])
    }
    $.ajax({
      url: "/api/ecosystems/sensors",
      type: "get",
      data: {ecosystems: UIDs, scope: "current"},
      async: true,
      success: function(currentSensorsData) {
        const dt = new Date(currentSensorsData[0]["datetime"]);
        $("#lastRecordTime").text("Last sensors measure at " + dt.toLocaleTimeString())
        gauges.fromCurrentSensorsData(currentSensorsData);
      }
    });
  },

  // System page
  createSystemBoardsGraphs: function(graphUpdatePeriod) {
    const updateCoeff = 1000 * 60 * graphUpdatePeriod;
    let now = new Date();
    now = new Date(Math.floor((now.getTime() - 10 * 1000) / updateCoeff) * updateCoeff);
    const dataID = "systemHistoricData";
    const storedData = sessionStorage.getItem(dataID);
    let download = true;
    if (storedData !== null) {
      const parsedData = JSON.parse(storedData);
      const lastUpdate = new Date(parsedData.lastUpdate)
      if (lastUpdate.valueOf() === now.valueOf()){
        download = false;
        graphs.create(parsedData.data);
      }
    }
    if (download) {
      $.ajax({
        url: "/api/system/data",
        type: "get",
        async: true,
        success: function(response) {
          const data = graphs.formatSystemHistoricData(response);
          sessionStorage.setItem(dataID, JSON.stringify({
            "lastUpdate": now, "data": data,
          }))
          graphs.create(data);
        }
      })
    }
    Object.assign(graphs.store, {updateDT: new Date().setSeconds(0, 0)});
  },

}
