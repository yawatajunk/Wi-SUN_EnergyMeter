var express = require('express');
var fs = require('fs')
var router = express.Router();

pow_file = '/tmp/curr_pow.txt'

/* GET inst_power page. */
router.get('/', function(req, res, next) {
  if (fs.existsSync(pow_file)) {
    power = fs.readFileSync(pow_file);
  }
  else {
    power = '';
  }
  
  res.render('inst_power', { inst_power: power });
});

module.exports = router;
