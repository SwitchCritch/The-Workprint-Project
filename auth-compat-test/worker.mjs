// Private authentication service. Deploy with workers_dev and preview_urls disabled.
import { scryptSync, timingSafeEqual, randomBytes } from "node:crypto";
import { Buffer } from "node:buffer";
const fixture = "scrypt:32768:8:1$public-test-salt$867a75bb83d09f72cbd2dd52e07bbe55ddb9329941d49110c4868f3127fb7e215bca5559d4298d58bb606a7a1812415a00c9bab9a7bac5baa94b15946c543404";
const options = {N:32768,r:8,p:1,maxmem:64*1024*1024};
const derive = (password,salt) => scryptSync(password,salt,64,options);
function verify(password,hash) {
  const parsed = /^scrypt:32768:8:1\$([A-Za-z0-9-]{1,64})\$([a-f0-9]{128})$/.exec(hash);
  if (!parsed) return false;
  return timingSafeEqual(derive(password,parsed[1]),Buffer.from(parsed[2],"hex"));
}
const reply = (body,status=200) => Response.json(body,{status,headers:{"Cache-Control":"no-store"}});
export default {
  async fetch(request) {
    const path = new URL(request.url).pathname;
    try {
      if (request.method==="GET" && path==="/self-test") {
        return reply({passed:verify("workprint-public-test",fixture) && !verify("wrong-password",fixture)});
      }
      if(request.method!=="POST" || !["/verify","/hash"].includes(path)) return reply({error:"not found"},404);
      const raw = await request.text();
      if(raw.length>8192) return reply({error:"invalid request"},400);
      const data=JSON.parse(raw);
      if(typeof data.password!=="string" || data.password.length>256 || data.password.length<1) return reply({error:"invalid request"},400);
      if(path==="/verify") return reply({valid:typeof data.hash==="string" && verify(data.password,data.hash)});
      if(data.password.length<12) return reply({error:"invalid request"},400);
      const salt=randomBytes(16).toString("hex");
      return reply({hash:"scrypt:32768:8:1$"+salt+"$"+derive(data.password,salt).toString("hex")});
    } catch { return reply({error:"authentication unavailable"},503); }
  }
};
