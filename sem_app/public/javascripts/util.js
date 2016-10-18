//
// aタグをクリックイベントに置換
//
$(function(){
    var a_tags = $('a');
    
    a_tags.each(function(){
        var url = $(this).attr('href');
        $(this).removeAttr('href');
        $(this).click(function(){
            location.href = url;
        });
    });
});
