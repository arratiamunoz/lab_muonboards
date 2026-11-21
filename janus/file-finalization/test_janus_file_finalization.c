
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "src/JanusC.h"
#include "src/FERSutils.h"
#include "src/Statistics.h"
#include "src/outputfiles.h"

extern FILE *of_list_c, *of_servInfo;
extern int offline_conn;
int StartRun(void);
int StopRun(void);
Stats_t Stats;
static int starts, stops, start_rc, stop_rc, saves, save_failures;
static int deny_info, write_fail, sync_fail;
static uint64_t wall = UINT64_C(1700000000000);
time_t __wrap_time(time_t *out) {
 time_t stamp=(time_t)(wall/1000);
 if (out) *out=stamp;
 return stamp;
}


FILE *__real_fopen(const char *, const char *);
FILE *__wrap_fopen(const char *path,const char *mode) {
	if (deny_info && strstr(path,"_Info.txt.partial")) {errno=EACCES; return NULL;}
	return __real_fopen(path,mode);
}
int __real_vfprintf(FILE *,const char*,va_list);
int __wrap_vfprintf(FILE *file,const char *fmt,va_list args) {
	if (write_fail && file && file == of_list_c) { errno=ENOSPC; return -1; }
	return __real_vfprintf(file,fmt,args);
}
int __real_fsync(int);
int __wrap_fsync(int fd) {
	if (sync_fail) { sync_fail=0; errno=EIO; return -1;}
	return __real_fsync(fd);
}
int Con_printf(const char *dst,const char *fmt,...) {
	(void)dst;
	if (strcmp(fmt,"Output file(s) saved in '%s' folder\n")==0) ++saves;
	if (strstr(fmt,"full output save not confirmed")) ++save_failures;
	return 0;
}
uint64_t j_get_time(void) { return wall; }
int FERS_GetLastError(char d[1024]) { strcpy(d,"offline stub"); return 0; }
int FERS_StartAcquisition(int *h,int b,int m,int r) { (void)h;(void)b;(void)m;(void)r; ++starts; return start_rc;}
int FERS_StopAcquisition(int *h,int b,int m,int r) { (void)h;(void)b;(void)m;(void)r; ++stops; return stop_rc;}
int FERS_ReadRegister(int h,uint32_t a,uint32_t *d) { (void)h;(void)a; *d=0;return 0;}
int FERS_SetParam(int h,const char *k,const char *v) { (void)h;(void)k;(void)v; return 0;}
int FERS_configure(int h,int m) { (void)h;(void)m; return 0;}
int FERS_GetParam(int h,const char *k,char *v) { (void)h;(void)k;*v=0;return 0;}
int FERS_GetParam_int(int h,const char *k) { (void)h;return !strcmp(k,"GainSelect")?GAIN_SEL_AUTO:0; }
float FERS_GetParam_float(int h,const char *k) { (void)h;(void)k;return 0; }
uint64_t FERS_GetParam_uint64(int h,const char *k) { (void)h;(void)k;return UINT64_MAX; }
int FERS_Get_CncPath(char *d,char *c) { (void)d;*c=0;return 0; }
int FERS_GetCncInfo(int h,FERS_CncInfo_t *c) { (void)h;memset(c,0,sizeof(*c));return 0; }
int FERS_GetBoardInfo(int h,FERS_BoardInfo_t *b) { (void)h;memset(b,0,sizeof(*b));b->pid=42420;strcpy(b->ModelName,"A5202");b->FPGA_FWrev=0xa7070800;return 0; }
int FERS_HV_Get_FWVer(int h,uint32_t *v) { (void)h;float x=6.4f;memcpy(v,&x,sizeof(x));return 0; }

static void write_text(const char *path,const char *s) {
	FILE *f=fopen(path,"w");assert(f);assert(fputs(s,f)!=EOF);assert(fclose(f)==0);
}
static char *contents(const char *path) {
	FILE *f=fopen(path,"r");assert(f);assert(fseek(f,0,SEEK_END)==0);long n=ftell(f);assert(n>=0);rewind(f);
	char *p=malloc((size_t)n+1);assert(p);assert(fread(p,1,(size_t)n,f)==(size_t)n);p[n]=0;assert(fclose(f)==0);return p;
}
static void old_unchanged(const char *p) {
	char *buf=contents(p);assert(strcmp(buf,"preserve original\n")==0);free(buf);
}
static void begin(int n) {
	RunVars.RunNumber=n;
	strcpy(J_cfg.DataFilePath,"DataFiles/");
	AcqStatus=ACQSTATUS_READY;
}
static void configured(void) {
	J_cfg.NumBrd=1;J_cfg.NumCh=64;J_cfg.AcquisitionMode=ACQMODE_SPECT;
	J_cfg.EHistoNbin=8192;J_cfg.StartRunMode=STARTRUN_ASYNC;
	J_cfg.OutFileEnableMask=OUTFILE_LIST_CSV|OUTFILE_SERVICE_INFO|OUTFILE_RUN_INFO;
	offline_conn=1;
}
static void finish_30m(void) {
	wall+=1800000;Stats.current_tstamp_us[0]=1800000000.0;
}
static void populate(void) {
	SpectEvent_t ev={0};ev.chmask=UINT64_MAX;
	for (int c=0;c<64;++c){ev.energyHG[c]=c+100;ev.energyLG[c]=c+10;}
	for (int i=0;i<6184;++i) assert(SaveList(0,1000.0+i*290000.0,(uint64_t)i,&ev,DTQ_SPECT)==0);
}
static void assert_missing(const char *p) {assert(access(p,F_OK)!=0 && errno==ENOENT);}
static void no_streams(void) {assert(!of_list_c && !of_servInfo);}
static void happy(void) {
	begin(100);
	assert(StartRun()==0);assert(starts==1);populate();
	finish_30m();
	assert(StopRun()==0);assert(stops==1 && saves==1 && save_failures==0);no_streams();
	assert(access("DataFiles/Run100_Info.txt",F_OK)==0);
	assert_missing("DataFiles/Run100_Info.txt.partial");
	char *text=contents("DataFiles/Run100_Info.txt");
	assert(strstr(text,"Elapsed time = 1800.000 s"));assert(strstr(text,"PID = 42420"));
	char *one=strstr(text,"FIXTURE_OPTION 1");assert(one);
#ifndef STOCK_TEST
	assert(!strstr(one+1,"FIXTURE_OPTION 1"));
#endif
	free(text);
	assert(StopRun()==0);assert(stops==1 && saves==1); /* repeated manual stop cannot rewrite metadata */
}
#ifndef STOCK_TEST
static int cookie_closes;
static ssize_t cookie_write(void *arg,const char *p,size_t n) { (void)arg;(void)p;(void)n;errno=ENOSPC; return -1; }
static int cookie_close(void *arg) { (void)arg;++cookie_closes;errno=EIO;return -1; }
#endif
int main(int argc,char **argv) {
	assert(argc==2); assert(chdir(argv[1])==0); assert(mkdir("DataFiles",0700)==0);
	write_text(CONFIG_FILENAME,"FIXTURE_OPTION 1\n");
	configured();
	happy();
#ifdef STOCK_TEST
	return 0;
#else
	begin(101);
	write_text("DataFiles/Run101_ServiceInfo.txt","preserve original\n");
	assert(StartRun()<0 && starts==1);no_streams();old_unchanged("DataFiles/Run101_ServiceInfo.txt");
	assert(access("DataFiles/Run101_list.csv",F_OK)==0);
	assert(StartRun()<0 && starts==1);no_streams();old_unchanged("DataFiles/Run101_ServiceInfo.txt");

	begin(102);start_rc=-42;
	assert(StartRun()==-42 && starts==2);no_streams();start_rc=0;
	assert(access("DataFiles/Run102_list.csv",F_OK)==0);assert_missing("DataFiles/Run102_Info.txt");
	assert(StartRun()<0 && starts==2);no_streams();

	begin(103);assert(StartRun()==0);assert(SaveList(0,1,1,&(SpectEvent_t){0},DTQ_SPECT)==0);
	deny_info=1;int prev=stops;assert(StopRun()<0 && stops==prev+1);deny_info=0;no_streams();
	assert_missing("DataFiles/Run103_Info.txt");assert_missing("DataFiles/Run103_Info.txt.partial");
	assert(StopRun()==0 && stops==prev+1);

	begin(104);assert(StartRun()==0);write_text("DataFiles/Run104_Info.txt","preserve original\n");
	assert(StopRun()<0);no_streams();old_unchanged("DataFiles/Run104_Info.txt");
	assert(access("DataFiles/Run104_Info.txt.partial",F_OK)==0);

	begin(105);assert(StartRun()==0);write_text("DataFiles/Run105_Info.txt.partial","preserve original\n");
	assert(StopRun()<0);no_streams();assert_missing("DataFiles/Run105_Info.txt");old_unchanged("DataFiles/Run105_Info.txt.partial");

	begin(106);assert(StartRun()==0);
	assert(fclose(of_list_c)==0);
	of_list_c=fopencookie(NULL,"w",(cookie_io_functions_t){.write=cookie_write,.close=cookie_close});assert(of_list_c);
	assert(fputs("buffered bytes",of_list_c)!=EOF);
	assert(fputs("independent service row\n",of_servInfo)!=EOF);
	assert(StopRun()<0 && cookie_closes==1);no_streams();
	assert_missing("DataFiles/Run106_Info.txt");
	char *service=contents("DataFiles/Run106_ServiceInfo.txt");
	assert(strstr(service,"independent service row\n"));free(service);
	assert(StopRun()==0 && cookie_closes==1);

	begin(107);write_fail=1;prev=stops;
	assert(StartRun()<0 && stops==prev+1);write_fail=0;no_streams();assert_missing("DataFiles/Run107_Info.txt");

	begin(108);assert(StartRun()==0);sync_fail=1;
	assert(StopRun()<0);no_streams();assert_missing("DataFiles/Run108_Info.txt");

	begin(109);assert(StartRun()==0);stop_rc=-43;
	assert(StopRun()==-43);no_streams();assert_missing("DataFiles/Run109_Info.txt");
	assert(saves==1 && save_failures==7);
	puts("PASS: exact patched JANUS StopRun/StartRun, 6,184 simulated 64-channel events, durable success, both duplicate protections, partial retention, data-first publication, independent flush/close, output-header stop, fsync failure, repeat stop, and original FERS error priority");
	return 0;
#endif
}

