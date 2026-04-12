const bcrypt = require('bcryptjs');

const email = 'mbs@modprojects.co.uk';
const password = 'Pool2024';

const hash = bcrypt.hashSync(password, 12);

console.log('\n=== Copy and paste this SQL into your Hostinger database manager ===\n');
console.log(`INSERT INTO users (email, password_hash, is_admin)
VALUES ('${email}', '${hash}', TRUE);`);
console.log('\n=================================================================\n');
