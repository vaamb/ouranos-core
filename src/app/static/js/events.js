const socket = io();

// Ping related functions
let ping_pong_times = [];
let start_time;

function ping() {
  start_time = (new Date).getTime();
  socket.volatile.emit('my_ping');
}

// Current date related functions
const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December'];

var now;
let day;
let month;
var formattedDate;

function formatDate(date) {
  day = days[date.getDay()];
  month = months[date.getMonth()];
  formattedDate = ''.concat(day, ' ', date.getDate(), ' ', month);
  return formattedDate
}

function updateTodayDate() {
  now = new Date();
  $('#today_date').text(formatDate(now));
}

// Function that auto rerun at midnight
var toRunAtMidnight = [];

function runAtMidnight() {
  const now = new Date();
  const midnight = new Date(now);
  midnight.setDate(midnight.getDate() + 1);
  midnight.setHours(0, 0, 0);

  const timeToMidnight = midnight - now;

  setTimeout(function() {
    runAtMidnight();
    for (const fct in toRunAtMidnight) {
      toRunAtMidnight[fct]();
    }
    }, timeToMidnight);
}

function updateLastRecordTime(date, text="Last record at ") {
  lastDataUpdate = new Date();
  if (date instanceof Date) {
    $("#lastRecordTime").text(text + date.toLocaleTimeString());
  } else {
    $("#lastRecordTime").text();
  }
}

// Call functions when ready
$(function () {
  runAtMidnight();

  updateTodayDate();
  toRunAtMidnight.push(updateTodayDate);

  ping();
  window.setInterval(ping, 1000);

  socket.on('my_pong', function() {
    let latency = (new Date).getTime() - start_time;
    ping_pong_times.push(latency);
    ping_pong_times = ping_pong_times.slice(-5);
    let sum = 0;
    for (let i = 0; i < ping_pong_times.length; i++)
      sum += ping_pong_times[i];
    $('#ping-pong').text((Math.round(10 * sum / ping_pong_times.length) / 10).toFixed(1));
  });
});