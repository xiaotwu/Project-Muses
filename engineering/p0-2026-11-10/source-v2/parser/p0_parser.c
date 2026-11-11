// SPDX-License-Identifier: MIT
// Independent native conservative slicer. Target shape mirrors YouTube.js
// 18.3.0's MIT nsigMatcher; it does not execute or emulate a whole player.
#include "p0_parser.h"
#include <tree_sitter/api.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdalign.h>
#include <setjmp.h>
#include <pthread.h>
#include <time.h>
#include <limits.h>
extern const TSLanguage *tree_sitter_javascript(void);
// Pinned Tree-sitter 0.25.10 exports these allocator slots. Restore the exact
// previous callbacks, not merely defaults, on every exit path.
extern void *(*ts_current_malloc)(size_t);
extern void *(*ts_current_calloc)(size_t,size_t);
extern void *(*ts_current_realloc)(void *,size_t);
extern void (*ts_current_free)(void *);
typedef union Block Block;
union Block { struct { Block *prev,*next; size_t size; } h; max_align_t alignment; };
typedef struct { uint32_t start,end; } Span;
typedef struct { Span node; char *key,*alias_owner; uint32_t same; unsigned kind; bool selected,analyze,solver,timestamp,has_init; } Record;
typedef struct Binding { const char *text; size_t length; struct Binding *next; } Binding;
typedef struct Scope { Binding *names; struct Scope *parent; } Scope;
typedef struct {
  jmp_buf escape; Block *blocks; size_t live,peak;
  p0_parser_limits limits; p0_parser_result *result;
  const char *input; size_t length; char *output; size_t capacity,used;
  Record *records; uint32_t count,record_capacity;
  uint32_t *table; size_t table_size; uint32_t *queue; size_t head,tail;
  char param_name[257],alias[257],alias_owner[257]; uint64_t started;
  TSParser *parser; size_t parse_offset,parse_length,header_length;
  uint32_t dependency_visits;
  void *(*previous_malloc)(size_t);void *(*previous_calloc)(size_t,size_t);
  void *(*previous_realloc)(void *,size_t);void (*previous_free)(void *);
} State;
static _Thread_local State *active;
static pthread_mutex_t owner=PTHREAD_MUTEX_INITIALIZER;
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static void fail(p0_parser_status status){active->result->status=status;longjmp(active->escape,1);}
static void check(void){if((active->limits.cancelled&&*active->limits.cancelled)||(active->limits.should_cancel&&active->limits.should_cancel(active->limits.cancel_context)))fail(P0_PARSE_CANCELLED);if(now_ns()>=active->limits.deadline_ns)fail(P0_PARSE_DEADLINE);}
static void *alloc(size_t n){
  State *s=active;size_t total=n+sizeof(Block);
  if(total<n||s->live>s->limits.max_working_bytes||total>s->limits.max_working_bytes-s->live)fail(P0_PARSE_MEMORY_LIMIT);
  Block *p=malloc(total);if(!p)fail(P0_PARSE_MEMORY_LIMIT);
  p->h=(typeof(p->h)){NULL,s->blocks,n};if(s->blocks)s->blocks->h.prev=p;s->blocks=p;
  s->live+=total;if(s->peak<s->live)s->peak=s->live;return p+1;
}
static void release(void *ptr){if(!ptr)return;Block *p=(Block *)ptr-1;if(p->h.prev)p->h.prev->h.next=p->h.next;else active->blocks=p->h.next;if(p->h.next)p->h.next->h.prev=p->h.prev;active->live-=p->h.size+sizeof(Block);free(p);}
static void *resize(void *ptr,size_t n){if(!ptr)return alloc(n);if(!n){release(ptr);return NULL;}Block *old=(Block *)ptr-1;size_t size=old->h.size;void *p=alloc(n);memcpy(p,ptr,n<size?n:size);release(ptr);return p;}
static void *zero(size_t count,size_t size){if(size&&count>SIZE_MAX/size)fail(P0_PARSE_MEMORY_LIMIT);size_t n=count*size;void *p=alloc(n);memset(p,0,n);return p;}
static bool type(TSNode n,const char *t){return !ts_node_is_null(n)&&!strcmp(ts_node_type(n),t);}
static TSNode field(TSNode n,const char *name){return ts_node_is_null(n)?(TSNode){0}:ts_node_child_by_field_name(n,name,(uint32_t)strlen(name));}
static TSNode safe_child(TSNode n,uint32_t i){return ts_node_is_null(n)?(TSNode){0}:ts_node_named_child(n,i);}
static uint32_t safe_count(TSNode n){return ts_node_is_null(n)?0:ts_node_named_child_count(n);}
// Tree-sitter's child accessors require a non-null node; malformed/truncated
// window probes deliberately encounter absent fields.
#define ts_node_named_child safe_child
#define ts_node_named_child_count safe_count
static size_t nlen(TSNode n){return ts_node_end_byte(n)-ts_node_start_byte(n);}
static const char *nstart(TSNode n){return active->input+active->parse_offset+ts_node_start_byte(n);}
static bool text_is(TSNode n,const char *text){return !ts_node_is_null(n)&&nlen(n)==strlen(text)&&!memcmp(nstart(n),text,nlen(n));}
static char *copy_node(TSNode n){size_t size=nlen(n);if(size>256)fail(P0_PARSE_UNSUPPORTED);char *p=alloc(size+1);memcpy(p,nstart(n),size);p[size]=0;return p;}
static uint64_t hash_text(const char *p,size_t n){uint64_t h=1469598103934665603ULL;for(size_t i=0;i<n;i++){h^=(unsigned char)p[i];h*=1099511628211ULL;}return h;}
static uint32_t lookup(const char *key,size_t len){State *s=active;size_t slot=hash_text(key,len)&(s->table_size-1);for(size_t n=0;n<s->table_size;n++,slot=(slot+1)&(s->table_size-1)){uint32_t v=s->table[slot];if(!v)return 0;Record *r=&s->records[v-1];if(strlen(r->key)==len&&!memcmp(r->key,key,len))return v;}fail(P0_PARSE_MEMORY_LIMIT);return 0;}
static void index_record(uint32_t v){State *s=active;Record *r=&s->records[v-1];size_t slot=hash_text(r->key,strlen(r->key))&(s->table_size-1);for(;;slot=(slot+1)&(s->table_size-1)){uint32_t old=s->table[slot];if(!old||!strcmp(r->key,s->records[old-1].key)){r->same=old;s->table[slot]=v;return;}}}
static bool assignable(TSNode n){return type(n,"identifier")||type(n,"member_expression")||type(n,"subscript_expression");}
static bool solver_match(TSNode fn);
static bool timestamp_match(TSNode node,unsigned depth);
static void add_record(TSNode node,TSNode init,TSNode key,unsigned kind,const char *alias_owner){
  State *s=active;if(s->count>=32768)fail(P0_PARSE_UNSUPPORTED);
  if(s->count==s->record_capacity){s->record_capacity=s->record_capacity?s->record_capacity*2:1024;s->records=resize(s->records,s->record_capacity*sizeof(Record));}
  Record *r=&s->records[s->count++];memset(r,0,sizeof(*r));r->node=(Span){(uint32_t)s->parse_offset+ts_node_start_byte(node),(uint32_t)s->parse_offset+ts_node_end_byte(node)};r->key=copy_node(key);r->kind=kind;r->has_init=!ts_node_is_null(init);
  r->solver=solver_match(init);r->timestamp=type(init,"function_expression")&&timestamp_match(init,0);
  if(alias_owner){r->alias_owner=alloc(strlen(alias_owner)+1);strcpy(r->alias_owner,alias_owner);}
  index_record(s->count);
}
static bool function(TSNode n){return type(n,"function_expression")||type(n,"function_declaration")||type(n,"arrow_function")||type(n,"generator_function")||type(n,"method_definition");}
static TSNode first_function(TSNode node,unsigned depth){
  if(depth>active->limits.max_depth)fail(P0_PARSE_UNSUPPORTED);
  if(type(node,"function_expression"))return node;
  for(uint32_t i=0;i<ts_node_named_child_count(node);i++){TSNode r=first_function(ts_node_named_child(node,i),depth+1);if(!ts_node_is_null(r))return r;}
  return (TSNode){0};
}
static void index_statement(TSNode node){
    State *s=active;char *alias=s->alias,*alias_owner=s->alias_owner;
    if(type(node,"variable_declaration")||type(node,"lexical_declaration")){
      alias[0]=alias_owner[0]=0;
      for(uint32_t j=0;j<ts_node_named_child_count(node);j++){TSNode d=ts_node_named_child(node,j);if(!type(d,"variable_declarator"))continue;TSNode name=field(d,"name");if(type(name,"identifier"))add_record(d,field(d,"value"),name,1,NULL);}
    }else if(type(node,"expression_statement")){
      TSNode assignment=ts_node_named_child(node,0);if(!type(assignment,"assignment_expression"))return;
      TSNode left=field(assignment,"left"),right=field(assignment,"right");if(!assignable(left))return;
      if(type(right,"member_expression")&&text_is(field(right,"property"),"prototype")){
        TSNode object=field(right,"object");if(!assignable(object))fail(P0_PARSE_UNSUPPORTED);
        if(nlen(left)>256||nlen(object)>256)fail(P0_PARSE_UNSUPPORTED);
        memcpy(alias,nstart(left),nlen(left));alias[nlen(left)]=0;memcpy(alias_owner,nstart(object),nlen(object));alias_owner[nlen(object)]=0;
      }else if(alias[0]){
        size_t len=strlen(alias);bool belongs=nlen(left)>=len&&!memcmp(nstart(left),alias,len)&&(nlen(left)==len||nstart(left)[len]=='.'||nstart(left)[len]=='[');
        if(!belongs)alias[0]=alias_owner[0]=0;
      }
      add_record(node,right,left,2,alias_owner[0]?alias_owner:NULL);
    }else if(type(node,"function_declaration")){alias[0]=alias_owner[0]=0;add_record(node,node,field(node,"name"),3,NULL);}
}
static void select_record(uint32_t v,bool analyze){Record *r=&active->records[v-1];r->selected=true;if(analyze&&!r->analyze){r->analyze=true;active->queue[active->tail++]=v;}}
static void select_key(const char *key,size_t length){
  State *s=active;bool changed=false;for(uint32_t v=lookup(key,length);v;v=s->records[v-1].same){if(!s->records[v-1].analyze)changed=true;select_record(v,true);}if(!changed)return;
  for(uint32_t i=0;i<s->count;i++){const char *owner=s->records[i].alias_owner;if(owner&&strlen(owner)==length&&!memcmp(owner,key,length))select_record(i+1,true);}
}
static bool literal(TSNode n,const char *value){return type(n,"string")&&nlen(n)==strlen(value)+2&&!memcmp(nstart(n)+1,value,strlen(value));}
static bool solver_match(TSNode fn){
  if(!type(fn,"function_expression"))return false;
  TSNode params=field(fn,"parameters");if(ts_node_named_child_count(params)<3)return false;
  TSNode first=ts_node_named_child(params,0);if(!type(first,"identifier")||!type(ts_node_named_child(params,1),"assignment_pattern")||!type(ts_node_named_child(params,2),"assignment_pattern"))return false;
  bool ctor=false,alr=false;TSNode body=field(fn,"body");
  for(uint32_t i=0;i<ts_node_named_child_count(body);i++){
    TSNode statement=ts_node_named_child(body,i);if(!type(statement,"expression_statement"))continue;
    TSNode expr=ts_node_named_child(statement,0);
    if(type(expr,"assignment_expression")){TSNode left=field(expr,"left"),right=field(expr,"right");if(type(left,"identifier")&&nlen(left)==nlen(first)&&!memcmp(nstart(left),nstart(first),nlen(first))&&type(right,"new_expression")&&type(field(right,"constructor"),"member_expression"))ctor=true;}
    if(type(expr,"call_expression")&&type(field(expr,"function"),"member_expression")){TSNode args=field(expr,"arguments");if(ts_node_named_child_count(args)==2&&literal(ts_node_named_child(args,0),"alr")&&literal(ts_node_named_child(args,1),"yes"))alr=true;}
  }return ctor&&alr;
}
static bool timestamp_match(TSNode node,unsigned depth){
  if(depth>active->limits.max_depth)fail(P0_PARSE_UNSUPPORTED);
  if(type(node,"pair")&&text_is(field(node,"key"),"signatureTimestamp"))return true;
  for(uint32_t i=0;i<ts_node_named_child_count(node);i++)if(timestamp_match(ts_node_named_child(node,i),depth+1))return true;
  return false;
}
static void targets(void){State *s=active;for(uint32_t i=0;i<s->count;i++){Record *r=&s->records[i];if(r->solver){s->result->solver_matches++;select_key(r->key,strlen(r->key));}if(r->timestamp){s->result->timestamp_matches++;for(uint32_t v=lookup(r->key,strlen(r->key));v;v=s->records[v-1].same)select_record(v,false);}}if(s->result->solver_matches!=1||!s->result->timestamp_matches)fail(P0_PARSE_UNSUPPORTED);}
static void bind_depth(Scope *scope,TSNode node,unsigned depth){if(ts_node_is_null(node))return;if(depth>active->limits.max_depth)fail(P0_PARSE_UNSUPPORTED);if(type(node,"identifier")||type(node,"shorthand_property_identifier_pattern")){Binding *b=alloc(sizeof(*b));*b=(Binding){nstart(node),nlen(node),scope->names};scope->names=b;return;}if(type(node,"assignment_pattern")||type(node,"object_assignment_pattern")){bind_depth(scope,field(node,"left"),depth+1);return;}if(type(node,"pair_pattern")){bind_depth(scope,field(node,"value"),depth+1);return;}for(uint32_t i=0;i<ts_node_named_child_count(node);i++)bind_depth(scope,ts_node_named_child(node,i),depth+1);}
static void bind(Scope *scope,TSNode node){bind_depth(scope,node,0);}
static bool local(Scope *scope,TSNode name){for(;scope;scope=scope->parent)for(Binding *b=scope->names;b;b=b->next)if(b->length==nlen(name)&&!memcmp(b->text,nstart(name),b->length))return true;return false;}
static void clear_scope(Scope *scope){Binding *b=scope->names;while(b){Binding *next=b->next;release(b);b=next;}}
static void vars(Scope *scope,TSNode node,unsigned depth){if(depth>active->limits.max_depth)fail(P0_PARSE_UNSUPPORTED);if(function(node))return;if(type(node,"variable_declaration"))for(uint32_t i=0;i<ts_node_named_child_count(node);i++){TSNode d=ts_node_named_child(node,i);if(type(d,"variable_declarator"))bind(scope,field(d,"name"));}for(uint32_t i=0;i<ts_node_named_child_count(node);i++)vars(scope,ts_node_named_child(node,i),depth+1);}
static void lexical(Scope *scope,TSNode node){for(uint32_t i=0;i<ts_node_named_child_count(node);i++){TSNode child=ts_node_named_child(node,i);if(type(child,"lexical_declaration")){for(uint32_t j=0;j<ts_node_named_child_count(child);j++){TSNode d=ts_node_named_child(child,j);if(type(d,"variable_declarator"))bind(scope,field(d,"name"));}}else if(type(child,"function_declaration")||type(child,"class_declaration"))bind(scope,field(child,"name"));}}
static void dependencies(TSNode node,Scope *scope,unsigned depth){
  if(ts_node_is_null(node))return;if(depth>active->limits.max_depth)fail(P0_PARSE_UNSUPPORTED);
  if(!(++active->dependency_visits%256))check();
  Scope inner={NULL,scope};bool enters=false;
  if(function(node)){enters=true;bind(&inner,field(node,"parameters"));bind(&inner,field(node,"parameter"));bind(&inner,field(node,"name"));vars(&inner,field(node,"body"),depth+1);}
  else if(type(node,"statement_block")||type(node,"for_statement")||type(node,"for_in_statement")){enters=true;lexical(&inner,node);}
  else if(type(node,"catch_clause")){enters=true;bind(&inner,field(node,"parameter"));}
  if(enters)scope=&inner;
  if(type(node,"identifier")||type(node,"shorthand_property_identifier")){if(!local(scope,node))select_key(nstart(node),nlen(node));}
  else if(type(node,"member_expression")||type(node,"subscript_expression")){
    TSNode root=node;while(type(root,"member_expression")||type(root,"subscript_expression"))root=field(root,"object");
    if(type(root,"identifier")&&!local(scope,root)&&nlen(node)<=256)select_key(nstart(node),nlen(node));
  }
  for(uint32_t i=0;i<ts_node_named_child_count(node);i++)dependencies(ts_node_named_child(node,i),scope,depth+1);
  if(enters)clear_scope(&inner);
}
static void emit(const char *bytes,size_t length){State *s=active;if(length>s->limits.max_output_bytes-s->used||length>=s->capacity-s->used)fail(P0_PARSE_OUTPUT_LIMIT);memcpy(s->output+s->used,bytes,length);s->used+=length;s->output[s->used]=0;}
static const char *read_input(void *payload,uint32_t offset,TSPoint point,uint32_t *length){(void)point;State *s=payload;check();if(offset>s->parse_length){*length=0;return "";}*length=(uint32_t)(s->parse_length-offset);return s->input+s->parse_offset+offset;}
static bool progress(TSParseState *state){(void)state;check();return false;}
static TSTree *parse_window(size_t offset,size_t length){
  State *s=active;s->parse_offset=offset;s->parse_length=length;ts_parser_reset(s->parser);
  TSInput in={s,read_input,TSInputEncodingUTF8,NULL};TSParseOptions opts={s,progress};uint64_t t=now_ns();
  TSTree *tree=ts_parser_parse_with_options(s->parser,NULL,in,opts);s->result->parse_ns+=now_ns()-t;if(!tree)fail(P0_PARSE_SYNTAX);return tree;
}
static void validate_tail(size_t offset){
  State *s=active;size_t tail=s->length-offset;if(tail>1024||s->header_length>1024)fail(P0_PARSE_UNSUPPORTED);
  size_t size=s->header_length+tail;char *joined=alloc(size+1);memcpy(joined,s->input,s->header_length);memcpy(joined+s->header_length,s->input+offset,tail);joined[size]=0;
  const char *saved=s->input;s->input=joined;TSTree *tree=parse_window(0,size);TSNode root=ts_tree_root_node(tree),fn=first_function(root,0);
  if(ts_node_has_error(root)||ts_node_is_null(fn)||!type(field(fn,"body"),"statement_block")||ts_node_named_child_count(field(fn,"body")))fail(P0_PARSE_SYNTAX);
  TSNode params=field(fn,"parameters");if(ts_node_named_child_count(params)!=1||!text_is(ts_node_named_child(params,0),s->param_name))fail(P0_PARSE_UNSUPPORTED);
  ts_tree_delete(tree);s->input=saved;release(joined);
}
static void build_index(void){
  State *s=active;s->table_size=65536;s->table=zero(s->table_size,sizeof(uint32_t));
  // Probe only possible opening braces in a bounded prefix. A syntactically
  // valid empty IIFE proves the header boundary; no truncated huge AST is kept.
  const char *full=s->input;char *header=alloc(1040);
  for(size_t end=1;end<s->length&&end<=1024;end++){
    if(full[end-1]!='{')continue;memcpy(header,full,end);memcpy(header+end,"})({});",7);s->input=header;
    TSTree *prefix=parse_window(0,end+7);TSNode root=ts_tree_root_node(prefix),fn=first_function(root,0),params=field(fn,"parameters"),body=field(fn,"body"),param=ts_node_named_child(params,0);
    bool valid=!ts_node_has_error(root)&&type(body,"statement_block")&&!ts_node_named_child_count(body)&&type(param,"identifier")&&nlen(param)<=256&&ts_node_named_child_count(params)==1&&ts_node_start_byte(body)+1==end;
    if(valid){memcpy(s->param_name,nstart(param),nlen(param));s->param_name[nlen(param)]=0;s->header_length=end;}
    ts_tree_delete(prefix);s->input=full;if(valid)break;
  }
  release(header);if(!s->header_length)fail(P0_PARSE_UNSUPPORTED);size_t offset=s->header_length;
  while(offset<s->length){
    check();while(offset<s->length&&(s->input[offset]==' '||s->input[offset]=='\n'||s->input[offset]=='\r'||s->input[offset]=='\t'))offset++;
    if(offset<s->length&&s->input[offset]=='}'){validate_tail(offset);offset=s->length;break;}
    size_t window=65536,consumed=0;
    for(;;){
      size_t length=s->length-offset;if(length>window)length=window;TSTree *tree=parse_window(offset,length);TSNode root=ts_tree_root_node(tree);uint32_t children=ts_node_named_child_count(root);
      uint32_t *ends=alloc((children+1)*sizeof(uint32_t));size_t candidates=0;
      // Keep the final node for the next window: EOF recovery/ASI must not be
      // mistaken for a complete statement. Tree-sitter handles lexical states.
      for(uint32_t i=0;i+1<children;i++){
        TSNode child=ts_node_named_child(root,i);if(ts_node_has_error(child)||type(child,"ERROR"))break;
        uint32_t end=ts_node_end_byte(child);char last=end?s->input[offset+end-1]:0;
        // Explicit terminators prevent EOF/ASI recovery from accepting just
        // the identifier of an assignment whose '=' lies beyond the window.
        if(last==';'||type(child,"comment")||((type(child,"function_declaration")||type(child,"class_declaration"))&&last=='}'))ends[candidates++]=end;
      }
      ts_tree_delete(tree);
      // Recovery may make an incomplete function look like several statements.
      // Reparse the proposed complete prefix with EOF and accept only a tree
      // with no missing/error nodes before retaining any declaration metadata.
      while(candidates){
        size_t end=ends[--candidates];TSTree *verified=parse_window(offset,end);TSNode valid_root=ts_tree_root_node(verified);
        if(!ts_node_has_error(valid_root)){
          for(uint32_t i=0;i<ts_node_named_child_count(valid_root);i++)index_statement(ts_node_named_child(valid_root,i));
          consumed=end;ts_tree_delete(verified);break;
        }
        ts_tree_delete(verified);
      }
      release(ends);
      if(consumed){offset+=consumed;break;}
      if(window>=256*1024||length==s->length-offset)fail(P0_PARSE_UNSUPPORTED);window*=2;
    }
  }
  s->queue=alloc(s->count*sizeof(uint32_t));s->result->declarations=s->count;
}
static void record_dependencies(Record *r){
  if(!r->has_init)return;TSTree *tree=parse_window(r->node.start,r->node.end-r->node.start);TSNode root=ts_tree_root_node(tree);
  if(ts_node_has_error(root))fail(P0_PARSE_SYNTAX);TSNode node=ts_node_named_child(root,0),init=node;
  if(type(node,"expression_statement")){TSNode expr=ts_node_named_child(node,0);init=type(expr,"assignment_expression")?field(expr,"right"):expr;}
  dependencies(init,NULL,0);check();ts_tree_delete(tree);
}
p0_parser_status p0_player_reduce(const char *input,size_t length,const p0_parser_limits *limits,char *output,size_t capacity,p0_parser_result *result){
  if(!result)return P0_PARSE_UNSUPPORTED;memset(result,0,sizeof(*result));result->input_bytes=length;
  if(!input||!output||!capacity){result->status=P0_PARSE_UNSUPPORTED;return result->status;}output[0]=0;
  if(pthread_mutex_trylock(&owner)){result->status=P0_PARSE_BUSY;return result->status;}
  State *s=calloc(1,sizeof(*s));if(!s){pthread_mutex_unlock(&owner);result->status=P0_PARSE_MEMORY_LIMIT;return result->status;}
  s->input=input;s->length=length;s->output=output;s->capacity=capacity;s->result=result;if(limits)s->limits=*limits;
  if(!s->limits.max_input_bytes)s->limits.max_input_bytes=4*1024*1024;if(!s->limits.max_working_bytes)s->limits.max_working_bytes=64*1024*1024;if(!s->limits.max_output_bytes)s->limits.max_output_bytes=256*1024;if(!s->limits.max_depth)s->limits.max_depth=256;if(!s->limits.deadline_ns)s->limits.deadline_ns=now_ns()+5000000000ULL;
  s->live=s->peak=sizeof(*s);active=s;
  s->previous_malloc=ts_current_malloc;s->previous_calloc=ts_current_calloc;s->previous_realloc=ts_current_realloc;s->previous_free=ts_current_free;
  if(!setjmp(s->escape)){
    if(length>s->limits.max_input_bytes||length>UINT32_MAX)fail(P0_PARSE_INPUT_LIMIT);check();
    ts_set_allocator(alloc,zero,resize,release);s->started=now_ns();
    s->parser=ts_parser_new();if(!ts_parser_set_language(s->parser,tree_sitter_javascript()))fail(P0_PARSE_UNSUPPORTED);
    uint64_t reduce_started=now_ns();build_index();targets();
    while(s->head<s->tail){check();Record *r=&s->records[s->queue[s->head++]-1];record_dependencies(r);}
    emit("(function(",10);emit(s->param_name,strlen(s->param_name));emit("){\n",3);
    for(uint32_t i=0;i<s->count;i++){if(!(i%128))check();if(s->records[i].selected){Record *r=&s->records[i];if(r->kind==1)emit("var ",4);emit(s->input+r->node.start,r->node.end-r->node.start);emit(";\n",2);result->selected_declarations++;}}
    emit("})({});\n",8);result->output_bytes=s->used;result->reduce_ns=now_ns()-reduce_started;
    ts_parser_delete(s->parser);result->status=P0_PARSE_OK;
  }
  // All parser and slicer allocation headers are tracked, including abandoned
  // partial trees. No C++/ObjC/Swift frames or destructors are crossed by jump.
  while(s->blocks)release(s->blocks+1);result->peak_working_bytes=s->peak;result->live_working_bytes=s->live-sizeof(*s);result->declarations=s->count;if(result->status!=P0_PARSE_OK){result->failure_offset=(uint32_t)s->parse_offset;result->parse_window_bytes=(uint32_t)s->parse_length;}
  // Cancellation during the final traversal/emission/cleanup must not publish
  // success. A late jump re-enters this cleanup with an empty allocation list.
  if(result->status==P0_PARSE_OK)check();
  ts_set_allocator(s->previous_malloc,s->previous_calloc,s->previous_realloc,s->previous_free);active=NULL;if(result->status!=P0_PARSE_OK){output[0]=0;result->output_bytes=0;}
  p0_parser_status status=result->status;free(s);pthread_mutex_unlock(&owner);return status;
}
const char *p0_parser_status_name(p0_parser_status s){static const char *names[]={"ok","input_limit","memory_limit","output_limit","cancelled","deadline","syntax","unsupported","busy"};return (unsigned)s<sizeof(names)/sizeof(*names)?names[s]:"unknown";}
