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
