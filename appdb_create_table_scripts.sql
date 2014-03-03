create table storypost (
	Id int(10) not null auto_increment,
	websiteUrl varchar(255) not null,
	registrationUrl varchar(255) not null,
	userId varchar(255) null default "",
	password varchar(200) null default "",
	storyPostedDate datetime,
	storyTitle text not null,
	storyUrl text default null,
	primary key (Id));

create table storyvote (
	tabId int(10) not null auto_increment,
	websiteUrl varchar(255) not null,
	voteUserId varchar(255) not null default "",
	votePasswd varchar(255) null default "",
	storyPosterUserId varchar(255) not null default "",
	votedStoryTitle text not null,
	votedStoryUrl text not null,
	voteDate datetime,
	storyPostDate datetime,
	voteCount int not null default 0,
	primary key (tabId));