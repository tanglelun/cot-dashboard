(function(){
  var form = document.querySelector('.nav-search');
  if(!form) return;
  var input = form.querySelector('input');
  if(!input) return;
  form.addEventListener('submit', function(e){
    e.preventDefault();
    var q = input.value.trim();
    if(q) window.location.href = 'search.html?q=' + encodeURIComponent(q);
  });
})();
