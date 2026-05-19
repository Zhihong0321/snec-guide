function HallIndex(pageKey, page, pageCount, searchValue,locale) {
  this.pageKey = pageKey || 'home';
  this.page = page;
  this.pageCount = pageCount;
  this.searchValue = searchValue;
  this.locale=locale || 'zh-CN';
  this.init();
}

HallIndex.prototype.init = function() {
  //company、product页面方法
  let pageKey = this.pageKey;
  let page = this.page;
  let pageCount = this.pageCount;
  let searchValue = this.searchValue;
  if (pageKey == 'product' || pageKey == 'company' || pageKey == 'companylist') {
    let $pagerDom;
    switch (pageKey) {
      case 'company':
        $pagerDom = document.getElementById('companyPager');
        break;
      case 'companylist':
        $pagerDom = document.getElementById('companyPager');
        break;
      case 'product':
        $pagerDom = document.getElementById('productPager');
        break;
    }
    let $btnSearch = document.getElementById('btnSearch');
    let $inputSearch = document.getElementById('inputSearch');
    if (searchValue) {
      $inputSearch.value = searchValue;
    }
    let pager = new Pager($pagerDom,{
      totlePageCount: pageCount, //总页数
      maxBtnCount: 3, //按钮数量最多有
      hasFirstLast:true,
      hasDots:true,
      locale:this.locale
    });
    pager.turnToPage(page);
    pager.onPageClick = function(e) {
      if (searchValue) {
        if (page != e) {
          window.location.href =
            '/hallIndex/' + pageKey + '/search/' + searchValue + '/page/' + e;
        }
      } else {
        if (page != e) {
          window.location.href = '/hallIndex/' + pageKey + '/page/' + e;
        }
      }
    };
    function search() {
      if ($inputSearch.value) {
        let value = $inputSearch.value.trim();
        window.location.href = '/hallIndex/' + pageKey + '/search/' + value;
      } else {
        window.location.href = '/hallIndex/' + pageKey;
      }
    }
    $btnSearch.onclick = function() {
      search();
    };
    $inputSearch.onkeydown = function() {
      if (event.keyCode == 13) {
        search();
      }
    };
  }
};
