// Private, fixed-vector self-test only. No database, secrets or real credentials.
import { scryptSync, timingSafeEqual } from "node:crypto";
const expected = Buffer.from("867a75bb83d09f72cbd2dd52e07bbe55ddb9329941d49110c4868f3127fb7e215bca5559d4298d58bb606a7a1812415a00c9bab9a7bac5baa94b15946c543404","hex");
export default {
  async fetch(request) {
    if (request.method !== "GET" || new URL(request.url).pathname !== "/self-test") {
      return new Response("Not found", {status:404});
    }
    try {
      const actual = scryptSync("workprint-public-test","public-test-salt",64,{N:32768,r:8,p:1,maxmem:64*1024*1024});
      return Response.json({passed: timingSafeEqual(actual,expected)}, {headers:{"Cache-Control":"no-store"}});
    } catch {
      return Response.json({passed:false,error:"scrypt unavailable"}, {status:503,headers:{"Cache-Control":"no-store"}});
    }
  }
};
